import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .backends import StorageBackendError, validate_object_key
from .models import StorageEndpoint, StorageObject, StorageScanJob
from .services import create_reference_ingestion_job, create_scan_job, scene_parts


@override_settings(ROOT_URLCONF="apps.storage_manager.test_urls", STORAGE_ALLOWED_ROOTS=[])
class StorageManagerTests(TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.admin = get_user_model().objects.create_user("storage-admin", password="test", is_staff=True)
        self.user = get_user_model().objects.create_user("storage-user", password="test")
        self.endpoint = StorageEndpoint.objects.create(
            name="测试目录",
            endpoint_type=StorageEndpoint.TYPE_LOCAL,
            root_uri=str(self.root),
            created_by=self.admin,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def tearDown(self):
        for path in sorted(self.root.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        self.root.rmdir()

    def write(self, relative, content=b"data"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    def test_scene_parts_recognizes_product_assets(self):
        self.assertEqual(scene_parts("AS05/scene.meta.xml"), ("scene", "AS05/scene", StorageObject.ROLE_METADATA))
        self.assertEqual(scene_parts("AS05/scene.thumb.jpg")[2], StorageObject.ROLE_THUMBNAIL)
        self.assertEqual(scene_parts("AS05/scene.tiff")[2], StorageObject.ROLE_DATA)
        self.assertEqual(
            scene_parts("scene/2025-12-06-07-52-28_UMBRA-10.stac.v2.json")[1],
            "scene/2025-12-06-07-52-28_UMBRA-10",
        )
        self.assertEqual(
            scene_parts("scene/2025-12-06-07-52-28_UMBRA-10_GEC.tif")[1],
            "scene/2025-12-06-07-52-28_UMBRA-10",
        )

    def test_object_key_rejects_absolute_and_traversal_paths(self):
        with self.assertRaises(StorageBackendError):
            validate_object_key("../secret.txt")
        with self.assertRaises(StorageBackendError):
            validate_object_key("C:/secret.txt")
        with self.assertRaises(StorageBackendError):
            validate_object_key("/secret.txt")

    def test_scan_creates_relative_objects_and_file_group_metadata(self):
        self.write("scene/AS05_001.tiff", b"a")
        self.write("scene/AS05_001.jpg", b"b")
        self.write("scene/AS05_001.meta.xml", b"<meta />")
        job = create_scan_job(endpoint=self.endpoint, user=self.admin, mode=StorageScanJob.MODE_FULL)

        self.assertEqual(job.status, StorageScanJob.STATUS_SUCCEEDED)
        self.assertEqual(job.files_scanned, 3)
        self.assertEqual(job.new_count, 3)
        self.assertEqual(job.scenes_found, 1)
        self.assertTrue(all(not Path(obj.object_key).is_absolute() for obj in StorageObject.objects.all()))
        metadata = StorageObject.objects.get(scene_role=StorageObject.ROLE_METADATA)
        self.assertEqual(metadata.scene_group_key, "scene/AS05_001")
        self.assertEqual(job.checkpoint["phase"], "completed")

    def test_incremental_scan_reports_unchanged_and_changed(self):
        self.write("scene.tiff", b"one")
        first = create_scan_job(endpoint=self.endpoint, user=self.admin, mode=StorageScanJob.MODE_FULL)
        self.assertEqual(first.new_count, 1)
        second = create_scan_job(endpoint=self.endpoint, user=self.admin, mode=StorageScanJob.MODE_INCREMENTAL)
        self.assertEqual(second.unchanged_count, 1)
        self.write("scene.tiff", b"two")
        third = create_scan_job(endpoint=self.endpoint, user=self.admin, mode=StorageScanJob.MODE_INCREMENTAL)
        self.assertEqual(third.changed_count, 1)
        self.assertEqual(StorageObject.objects.get().status, StorageObject.STATUS_CHANGED)

    def test_missing_requires_two_scans_and_does_not_delete_object(self):
        self.write("gone.tiff")
        create_scan_job(endpoint=self.endpoint, user=self.admin, mode=StorageScanJob.MODE_FULL)
        (self.root / "gone.tiff").unlink()
        first_missing = create_scan_job(endpoint=self.endpoint, user=self.admin, mode=StorageScanJob.MODE_INCREMENTAL)
        obj = StorageObject.objects.get()
        self.assertEqual(first_missing.missing_count, 1)
        self.assertFalse(obj.missing_confirmed)
        second_missing = create_scan_job(endpoint=self.endpoint, user=self.admin, mode=StorageScanJob.MODE_INCREMENTAL)
        obj.refresh_from_db()
        self.assertEqual(second_missing.missing_count, 1)
        self.assertTrue(obj.missing_confirmed)
        self.assertEqual(StorageObject.objects.count(), 1)

    def test_health_check_and_unsupported_backend(self):
        job = create_scan_job(endpoint=self.endpoint, user=self.admin, mode=StorageScanJob.MODE_HEALTH_CHECK)
        self.assertEqual(job.status, StorageScanJob.STATUS_SUCCEEDED)
        self.endpoint.endpoint_type = StorageEndpoint.TYPE_S3
        self.endpoint.save(update_fields=["endpoint_type"])
        failed = create_scan_job(endpoint=self.endpoint, user=self.admin)
        self.assertEqual(failed.status, StorageScanJob.STATUS_FAILED)
        self.assertIn("暂不支持", failed.error_message)

    def test_non_admin_cannot_scan(self):
        with self.assertRaises(PermissionError):
            create_scan_job(endpoint=self.endpoint, user=self.user)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/storage/endpoints").status_code, 403)
        self.assertEqual(self.client.get("/api/storage/objects").status_code, 403)

    def test_disabled_endpoint_cannot_scan(self):
        self.endpoint.enabled = False
        self.endpoint.save(update_fields=["enabled", "updated_at"])
        response = self.client.post(f"/api/storage/endpoints/{self.endpoint.pk}/scan", {"mode": "full"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_api_does_not_return_secret_or_absolute_object_root(self):
        response = self.client.post("/api/storage/endpoints", {
            "name": "API目录",
            "endpoint_type": "local_directory",
            "root_uri": str(self.root),
            "credential_ref": "windows-credential/storage-readonly",
        }, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertNotIn("credential_ref", response.data)
        self.assertTrue(response.data["has_credential"])
        self.write("a.tif")
        scan = self.client.post(f"/api/storage/endpoints/{response.data['id']}/scan", {"mode": "full"}, format="json")
        self.assertEqual(scan.status_code, 201)
        objects = self.client.get("/api/storage/objects").data
        self.assertEqual(objects[0]["object_key"], "a.tif")
        self.assertNotIn(str(self.root), json.dumps(objects, default=str))

    def test_api_scan_and_job_listing(self):
        self.write("a.tif")
        response = self.client.post(f"/api/storage/endpoints/{self.endpoint.pk}/scan", {"mode": "full"}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.client.get("/api/storage/scan-jobs").status_code, 200)
        self.assertEqual(self.client.get(f"/api/storage/scan-jobs/{response.data['id']}").status_code, 200)

    def test_management_command_scans_endpoint(self):
        self.write("command.tif")
        output = tempfile.TemporaryFile(mode="w+")
        call_command("scan_storage", str(self.endpoint.pk), "--mode", "full", "--username", self.admin.username, stdout=output)
        self.assertTrue(StorageObject.objects.filter(object_key="command.tif").exists())

    def test_reference_ingestion_creates_job_without_copying_source(self):
        self.write("scene/AS05_JH_JS_003500_E111.4_N24.8_20260407150037_L2_HH_09_001.tiff", b"source")
        self.write("scene/AS05_JH_JS_003500_E111.4_N24.8_20260407150037_L2_HH_09_001.jpg", b"preview")
        create_scan_job(endpoint=self.endpoint, user=self.admin, mode=StorageScanJob.MODE_FULL)
        object_ids = list(StorageObject.objects.values_list("id", flat=True))
        from apps.ingestion.models import IngestionJob

        job = create_reference_ingestion_job(endpoint=self.endpoint, user=self.admin, object_ids=object_ids)
        self.assertEqual(job.source_type, IngestionJob.SOURCE_STORAGE_REFERENCE)
        self.assertEqual(job.items.count(), 1)
        self.assertEqual(Path(job.items.first().raw_path), self.root / "scene")
