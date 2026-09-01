import json
import hashlib
import tempfile
import zipfile
from pathlib import Path
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.imagery.models import ImageryAsset, ImageryRecord
from .models import DeliveryBasketItem, DeliverySnapshot, ExportJob
from .services import process_pending


@override_settings(EXPORTS_DIR=Path(tempfile.gettempdir()) / "airmap-delivery-tests")
class DeliveryTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user("delivery-a", password="pw")
        self.other = User.objects.create_user("delivery-b", password="pw")
        self.client = APIClient(); self.client.force_authenticate(self.user)
        self.root = Path(tempfile.mkdtemp())
        self.image = ImageryRecord.objects.create(id="delivery-image", scene_key="scene-one", identity_hash="delivery-hash", stac_id="scene-one", source_name="scene-one.tif", first_uploaded_by=self.user, geometry={"type":"Polygon","coordinates":[[[1,1],[2,1],[2,2],[1,1]]]}, bbox=[1,1,2,2])
        data = self.root / "scene-one.tif"; data.write_bytes(b"fake raster")
        ImageryAsset.objects.create(imagery=self.image, role="data", name=data.name, path=str(data), size_bytes=data.stat().st_size)
        for role, name, content in (
            ("preview", "scene-one.jpg", b"preview"),
            ("thumbnail", "scene-one.thumb.jpg", b"thumb"),
            ("metadata", "scene-one.meta.xml", b"<meta/>"),
            ("incidence", "scene-one.meta.incidence.xml", b"<incidence/>"),
            ("log", "scene-one.log", b"log"),
        ):
            asset_path = self.root / name
            asset_path.write_bytes(content)
            ImageryAsset.objects.create(imagery=self.image, role=role, name=name, path=str(asset_path), size_bytes=len(content))

    def test_basket_isolated_and_deduplicated(self):
        self.assertEqual(self.client.post("/api/delivery/basket", {"imagery_ids": [self.image.id, self.image.id]}, format="json").status_code, 200)
        self.assertEqual(DeliveryBasketItem.objects.count(), 1)
        other = APIClient(); other.force_authenticate(self.other)
        self.assertEqual(other.get("/api/delivery/basket").json()["count"], 0)

    def test_manifest_export_and_download_permission(self):
        self.client.post("/api/delivery/basket", {"imagery_ids": [self.image.id]}, format="json")
        response = self.client.post("/api/delivery/exports", {"format": "manifest"}, format="json")
        self.assertEqual(response.status_code, 202)
        job = ExportJob.objects.get()
        process_pending(1)
        job.refresh_from_db(); self.assertEqual(job.status, "done")
        payload = json.loads(Path(job.file_path).read_text(encoding="utf-8")); self.assertEqual(payload["items"][0]["id"], self.image.id)
        self.assertIn("/api/access/signed-assets/", payload["items"][0]["assets"]["data"])
        data_detail = next(item for item in payload["items"][0]["asset_details"] if item["role"] == "data")
        self.assertEqual(data_detail["size_bytes"], len(b"fake raster"))
        self.assertEqual(data_detail["checksum_sha256"], hashlib.sha256(b"fake raster").hexdigest())
        self.assertEqual(data_detail["media_type"], "image/tiff")
        other = APIClient(); other.force_authenticate(self.other)
        self.assertEqual(other.get(f"/api/delivery/downloads/{job.id}").status_code, 404)

    def test_archived_image_fails_export(self):
        self.client.post("/api/delivery/basket", {"imagery_ids": [self.image.id]}, format="json")
        self.image.is_archived = True; self.image.save(update_fields=["is_archived"])
        response = self.client.post("/api/delivery/exports", {"format": "zip"}, format="json")
        self.assertEqual(response.status_code, 400)

    def test_clear_compatibility_endpoint(self):
        self.client.post("/api/delivery/basket", {"imagery_ids": [self.image.id]}, format="json")
        response = self.client.post("/api/delivery/basket/clear", {}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)

    def test_stac_export_is_json(self):
        self.client.post("/api/delivery/basket", {"imagery_ids": [self.image.id]}, format="json")
        job = ExportJob.objects.create(owner=self.user, format="stac", imagery_ids=[self.image.id])
        process_pending(1); job.refresh_from_db()
        self.assertEqual(job.status, "done")
        self.assertEqual(Path(job.file_path).suffix, ".json")
        self.assertEqual(json.loads(Path(job.file_path).read_text())["type"], "FeatureCollection")

    def test_zip_export_contains_all_assets_checksums_and_safe_member_names(self):
        self.image.scene_key = r"..\evil/../../scene:one"
        self.image.save(update_fields=["scene_key"])
        self.client.post("/api/delivery/basket", {"imagery_ids": [self.image.id]}, format="json")
        job = ExportJob.objects.create(owner=self.user, format="zip", imagery_ids=[self.image.id])
        process_pending(1); job.refresh_from_db()
        self.assertEqual(job.status, "done")
        with zipfile.ZipFile(job.file_path) as archive:
            names = archive.namelist()
            checksums = archive.read("checksums.sha256").decode("utf-8").splitlines()
        self.assertIn("manifest.json", names)
        self.assertIn("checksums.sha256", names)
        self.assertTrue(any("/data/" in name for name in names))
        self.assertTrue(any("/preview/" in name for name in names))
        self.assertTrue(any("/thumbnail/" in name for name in names))
        self.assertTrue(any("/metadata/" in name for name in names))
        self.assertTrue(any("/incidence/" in name for name in names))
        self.assertTrue(any("/log/" in name for name in names))
        data_names = [name for name in names if "/data/" in name]
        self.assertEqual(len(data_names), 1)
        self.assertNotIn("..", data_names[0])
        self.assertNotIn("\\", data_names[0])
        checksum_map = {path: digest for digest, path in (line.split("  ", 1) for line in checksums)}
        self.assertEqual(checksum_map[data_names[0]], hashlib.sha256(b"fake raster").hexdigest())
        with zipfile.ZipFile(job.file_path) as archive:
            self.assertEqual(hashlib.sha256(archive.read(data_names[0])).hexdigest(), checksum_map[data_names[0]])

    def test_missing_download_file_is_404(self):
        job = ExportJob.objects.create(owner=self.user, format="manifest", imagery_ids=[self.image.id], status="done", file_path=str(self.root / "gone.json"))
        self.assertEqual(self.client.get(f"/api/delivery/downloads/{job.id}").status_code, 404)

    def test_delivery_snapshot_freezes_basket_and_can_export(self):
        self.client.post("/api/delivery/basket", {"imagery_ids": [self.image.id]}, format="json")
        response = self.client.post("/api/delivery/snapshots", {"name": "售前交付版", "description": "冻结版本"}, format="json")
        self.assertEqual(response.status_code, 201)
        snapshot = DeliverySnapshot.objects.get()
        self.assertEqual(snapshot.imagery_ids, [self.image.id])
        self.client.post("/api/delivery/basket/clear", {}, format="json")
        export = self.client.post(f"/api/delivery/snapshots/{snapshot.id}", {"format": "manifest"}, format="json")
        self.assertEqual(export.status_code, 202)
        job = ExportJob.objects.get(snapshot=snapshot)
        self.assertEqual(job.imagery_ids, [self.image.id])
