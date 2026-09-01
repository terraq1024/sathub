import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.imagery.models import ImageryAsset, ImageryRecord

from .exceptions import ProcessingError
from .models import ProcessingJob
from .services import claim_next_job, expected_output_path, process_job


User = get_user_model()


class ProcessingTests(TestCase):
    def setUp(self):
        self.tempdir = TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.data_dir = Path(self.tempdir.name) / "data"
        self.processing_dir = self.data_dir / "processing"
        self.data_dir.mkdir(parents=True)
        self.processing_dir.mkdir(parents=True)
        self.settings_override = override_settings(
            DATA_DIR=self.data_dir,
            PROCESSING_DIR=self.processing_dir,
            TITILER_PYTHON=Path(sys.executable),
            PROCESSING_TIMEOUT_SECONDS=5,
        )
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

        self.owner = User.objects.create_user(username="owner", password="pw")
        self.other = User.objects.create_user(username="other", password="pw")
        self.admin = User.objects.create_superuser(
            username="admin",
            password="pw",
            email="admin@example.com",
        )
        self.imagery = self.create_imagery(self.owner, "image-1")
        self.client = APIClient()

    def create_imagery(self, owner, image_id, *, archived=False, source_path=None):
        if source_path is None:
            source_path = self.data_dir / "imagery" / image_id / "data" / f"{image_id}.tif"
        source_path.parent.mkdir(parents=True, exist_ok=True)
        source_path.write_bytes(b"test-raster-placeholder")
        imagery = ImageryRecord.objects.create(
            id=image_id,
            scene_key=f"scene-{image_id}",
            identity_hash=image_id.encode().hex().ljust(64, "0")[:64],
            stac_id=f"scene-{image_id}",
            source_name=f"scene-{image_id}",
            first_uploaded_by=owner,
            status=ImageryRecord.STATUS_READY,
            is_archived=archived,
            bbox=[10.0, 20.0, 12.0, 22.0],
            geometry={
                "type": "Polygon",
                "coordinates": [
                    [[10, 20], [12, 20], [12, 22], [10, 22], [10, 20]]
                ],
            },
        )
        ImageryAsset.objects.create(
            imagery=imagery,
            role=ImageryAsset.ROLE_DATA,
            name=source_path.name,
            path=str(source_path),
            media_type="image/tiff",
            size_bytes=source_path.stat().st_size,
        )
        return imagery

    def payload(self, imagery=None, **changes):
        value = {
            "imagery_id": (imagery or self.imagery).pk,
            "crop_geometry_type": ProcessingJob.CROP_BBOX,
            "bbox": [10, 20, 12, 22],
            "bands": [1, 2],
            "output_format": ProcessingJob.OUTPUT_GEOTIFF,
        }
        value.update(changes)
        return value

    def create_job(self, user=None, **changes):
        values = {
            "imagery": self.imagery,
            "created_by": user or self.owner,
            "crop_geometry_type": ProcessingJob.CROP_BBOX,
            "bbox": [10, 20, 12, 22],
            "bands": [1],
            "output_format": ProcessingJob.OUTPUT_GEOTIFF,
        }
        values.update(changes)
        return ProcessingJob.objects.create(**values)

    def authenticate(self, user):
        self.client.force_authenticate(user=user)

    def test_any_user_can_create_from_unarchived_imagery(self):
        self.authenticate(self.other)
        response = self.client.post("/api/processing/jobs", self.payload(), format="json")
        self.assertEqual(response.status_code, 201, response.data)
        job = ProcessingJob.objects.get(pk=response.data["id"])
        self.assertEqual(job.created_by, self.other)
        self.assertEqual(job.bands, [1, 2])

    def test_archived_imagery_cannot_be_processed(self):
        archived = self.create_imagery(self.owner, "image-archived", archived=True)
        self.authenticate(self.admin)
        response = self.client.post(
            "/api/processing/jobs",
            self.payload(archived),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("已归档", str(response.data))

    def test_source_asset_must_be_inside_data_dir(self):
        outside = Path(self.tempdir.name) / "outside.tif"
        imagery = self.create_imagery(self.owner, "image-outside", source_path=outside)
        self.authenticate(self.owner)
        response = self.client.post(
            "/api/processing/jobs",
            self.payload(imagery),
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("DATA_DIR", str(response.data))

    def test_bbox_polygon_bands_and_expression_validation(self):
        self.authenticate(self.owner)
        polygon_payload = self.payload(
            crop_geometry_type=ProcessingJob.CROP_POLYGON,
            bbox=None,
            geometry={
                "type": "Polygon",
                "coordinates": [
                    [[10, 20], [12, 20], [12, 22], [10, 20]]
                ],
            },
            bands=[],
            expression="(b1 - b2) / (b1 + b2)",
        )
        response = self.client.post(
            "/api/processing/jobs",
            polygon_payload,
            format="json",
        )
        self.assertEqual(response.status_code, 201, response.data)
        job = ProcessingJob.objects.get(pk=response.data["id"])
        self.assertIsNone(job.bbox)
        self.assertEqual(job.bands, [])

        invalid = self.payload(expression="__import__('os').system('dir')")
        response = self.client.post("/api/processing/jobs", invalid, format="json")
        self.assertEqual(response.status_code, 400)

        invalid = self.payload(expression="b1+b2")
        response = self.client.post("/api/processing/jobs", invalid, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("不能同时", str(response.data))

        invalid = self.payload(bands=[])
        response = self.client.post("/api/processing/jobs", invalid, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("至少需要", str(response.data))

    def test_job_visibility_and_admin_access(self):
        owner_job = self.create_job()
        other_job = self.create_job(user=self.other)

        self.authenticate(self.owner)
        response = self.client.get("/api/processing/jobs")
        self.assertEqual([item["id"] for item in response.data], [str(owner_job.id)])
        self.assertEqual(
            self.client.get(f"/api/processing/jobs/{other_job.id}").status_code,
            404,
        )

        self.authenticate(self.admin)
        response = self.client.get("/api/processing/jobs")
        self.assertEqual(len(response.data), 2)
        self.assertEqual(
            self.client.get(f"/api/processing/jobs/{owner_job.id}").status_code,
            200,
        )

    def test_pending_job_can_be_patched_but_running_job_cannot(self):
        job = self.create_job()
        self.authenticate(self.owner)
        response = self.client.patch(
            f"/api/processing/jobs/{job.id}",
            {"expression": "b1 / (b2 + 1)"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.data)
        job.refresh_from_db()
        self.assertEqual(job.bands, [])
        self.assertEqual(job.expression, "b1 / (b2 + 1)")

        job.status = ProcessingJob.STATUS_RUNNING
        job.save(update_fields=["status"])
        response = self.client.patch(
            f"/api/processing/jobs/{job.id}",
            {"bands": [1]},
            format="json",
        )
        self.assertEqual(response.status_code, 409)

    def test_retry_only_failed_job_and_owner_or_admin(self):
        job = self.create_job(
            status=ProcessingJob.STATUS_FAILED,
            error_message="失败",
            finished_at=None,
        )
        job_dir = self.processing_dir / str(job.id)
        job_dir.mkdir()
        (job_dir / "old.tmp").write_bytes(b"old")

        self.authenticate(self.other)
        self.assertEqual(
            self.client.post(f"/api/processing/jobs/{job.id}/retry").status_code,
            404,
        )
        self.authenticate(self.admin)
        response = self.client.post(f"/api/processing/jobs/{job.id}/retry")
        self.assertEqual(response.status_code, 202, response.data)
        job.refresh_from_db()
        self.assertEqual(job.status, ProcessingJob.STATUS_PENDING)
        self.assertFalse(job_dir.exists())

        response = self.client.post(f"/api/processing/jobs/{job.id}/retry")
        self.assertEqual(response.status_code, 409)

    def test_archived_imagery_blocks_queued_execution_and_retry(self):
        queued = self.create_job()
        failed = self.create_job(status=ProcessingJob.STATUS_FAILED)
        self.imagery.is_archived = True
        self.imagery.save(update_fields=["is_archived"])

        with self.assertRaises(ProcessingError):
            process_job(queued)
        queued.refresh_from_db()
        self.assertEqual(queued.status, ProcessingJob.STATUS_FAILED)
        self.assertIn("已归档", queued.error_message)

        self.authenticate(self.owner)
        response = self.client.post(f"/api/processing/jobs/{failed.id}/retry")
        self.assertEqual(response.status_code, 409)
        self.assertIn("已归档", str(response.data))

    def test_download_is_owner_or_admin_only_and_checks_output_boundary(self):
        job = self.create_job(status=ProcessingJob.STATUS_SUCCEEDED)
        target = expected_output_path(job)
        target.parent.mkdir(parents=True)
        target.write_bytes(b"result")
        job.output_path = str(target)
        job.output_media_type = "image/tiff"
        job.save(update_fields=["output_path", "output_media_type"])

        self.authenticate(self.other)
        self.assertEqual(
            self.client.get(f"/api/processing/jobs/{job.id}/download").status_code,
            404,
        )
        for user in (self.owner, self.admin):
            self.authenticate(user)
            response = self.client.get(f"/api/processing/jobs/{job.id}/download")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(b"".join(response.streaming_content), b"result")

        outside = Path(self.tempdir.name) / "stolen.tif"
        outside.write_bytes(b"outside")
        job.output_path = str(outside)
        job.save(update_fields=["output_path"])
        self.authenticate(self.owner)
        self.assertEqual(
            self.client.get(f"/api/processing/jobs/{job.id}/download").status_code,
            404,
        )

    def test_delete_rejects_running_and_cleans_known_job_directory(self):
        running = self.create_job(status=ProcessingJob.STATUS_RUNNING)
        self.authenticate(self.owner)
        self.assertEqual(
            self.client.delete(f"/api/processing/jobs/{running.id}").status_code,
            409,
        )

        failed = self.create_job(status=ProcessingJob.STATUS_FAILED)
        directory = self.processing_dir / str(failed.id)
        directory.mkdir()
        (directory / "result.tif").write_bytes(b"result")
        self.assertEqual(
            self.client.delete(f"/api/processing/jobs/{failed.id}").status_code,
            204,
        )
        self.assertFalse(directory.exists())

    def test_process_job_uses_subprocess_and_atomically_commits_output(self):
        job = self.create_job()

        def fake_run(command, **kwargs):
            payload = json.loads(kwargs["input"])
            temporary = Path(payload["output_path"])
            self.assertEqual(Path(payload["source_path"]).resolve().parents[3], self.data_dir.resolve())
            temporary.write_bytes(b"generated-raster")
            return subprocess.CompletedProcess(
                command,
                0,
                stdout=json.dumps({"width": 2, "height": 2, "count": 1}),
                stderr="",
            )

        with patch("apps.processing.services.subprocess.run", side_effect=fake_run) as runner:
            target = process_job(job)

        job.refresh_from_db()
        self.assertEqual(job.status, ProcessingJob.STATUS_SUCCEEDED)
        self.assertEqual(job.attempts, 1)
        self.assertEqual(Path(job.output_path), target)
        self.assertEqual(target.read_bytes(), b"generated-raster")
        self.assertEqual(target, expected_output_path(job))
        self.assertFalse(list(target.parent.glob("*.tmp.tif")))
        self.assertEqual(runner.call_args.kwargs["timeout"], 5)

    def test_subprocess_timeout_marks_failed_and_cleans_temporary_output(self):
        job = self.create_job()

        def timeout(command, **kwargs):
            Path(json.loads(kwargs["input"])["output_path"]).write_bytes(b"partial")
            raise subprocess.TimeoutExpired(command, kwargs["timeout"], stderr="x" * 5000)

        with patch("apps.processing.services.subprocess.run", side_effect=timeout):
            with self.assertRaises(ProcessingError):
                process_job(job)

        job.refresh_from_db()
        self.assertEqual(job.status, ProcessingJob.STATUS_FAILED)
        self.assertIn("超时", job.error_message)
        self.assertLessEqual(len(job.error_message), 8000)
        self.assertFalse(list((self.processing_dir / str(job.id)).glob("*.tmp.tif")))

    def test_claim_next_job_sets_running_state(self):
        job = self.create_job()
        claimed = claim_next_job()
        self.assertEqual(claimed.pk, job.pk)
        self.assertEqual(claimed.status, ProcessingJob.STATUS_RUNNING)
        self.assertEqual(claimed.attempts, 1)


class RasterWorkerSmokeTests(TestCase):
    def test_titiler_runtime_processes_geotiff_and_png(self):
        python = Path(settings.TITILER_PYTHON)
        worker = Path(__file__).with_name("raster_worker.py")
        if not python.is_file():
            self.skipTest("TITILER_PYTHON 不存在")
        probe = subprocess.run(
            [str(python), "-c", "import numpy,rasterio"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if probe.returncode:
            self.skipTest("TITILER_PYTHON 无法导入 rasterio/numpy")

        with TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            source = temp / "source.tif"
            creator = (
                "import sys,numpy as np,rasterio;"
                "from rasterio.transform import from_origin;"
                "p=sys.argv[1];"
                "a=np.stack([np.arange(16,dtype='uint16').reshape(4,4)+i for i in range(3)]);"
                "d=rasterio.open(p,'w',driver='GTiff',height=4,width=4,count=3,dtype='uint16',"
                "crs='EPSG:4326',transform=from_origin(10,22,.5,.5));"
                "d.write(a);d.close()"
            )
            created = subprocess.run(
                [str(python), "-c", creator, str(source)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(created.returncode, 0, created.stderr)

            cases = [
                ("geotiff", [1, 2], "", temp / "crop.tif"),
                ("png", [], "(b1-b2)/(b1+b2)", temp / "crop.png"),
            ]
            for output_format, bands, expression, output in cases:
                payload = {
                    "source_path": str(source),
                    "output_path": str(output),
                    "crop_geometry_type": "bbox",
                    "bbox": [10, 20, 12, 22],
                    "geometry": None,
                    "bands": bands,
                    "expression": expression,
                    "output_format": output_format,
                }
                result = subprocess.run(
                    [str(python), str(worker)],
                    input=json.dumps(payload),
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=60,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                metadata = json.loads(result.stdout)
                self.assertGreater(metadata["width"], 0)
                self.assertGreater(output.stat().st_size, 0)
