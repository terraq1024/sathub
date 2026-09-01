import io
import zipfile

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.imagery.models import ImageryRecord

from .models import IngestionItem, IngestionJob


class IngestionApiTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="u", password="p")
        self.project = Project.objects.create(name="Demo", code="demo", created_by=self.user)
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_url_import_creates_job_and_items(self):
        response = self.client.post(
            "/api/ingestion/jobs/url-import",
            {"project_id": self.project.id, "urls": "https://example.test/a.tif\nhttps://example.test/b.zip"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        job = IngestionJob.objects.get()
        self.assertEqual(job.source_type, IngestionJob.SOURCE_URL_TEXT)
        self.assertEqual(job.total_count, 2)
        self.assertEqual(IngestionItem.objects.count(), 2)

    def test_url_import_can_omit_project(self):
        response = self.client.post(
            "/api/ingestion/jobs/url-import",
            {"urls": "https://example.test/scene.7z"},
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(IngestionJob.objects.get().project_id)

    def test_zip_upload_creates_staged_job(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr("AS05_AR_TD_003485_E117.1_N31.3_20260406020232_L2_HH_05_001.tif", b"not-a-real-tif")
        upload = SimpleUploadedFile("sample.zip", buffer.getvalue(), content_type="application/zip")

        response = self.client.post(
            "/api/ingestion/jobs/upload-zip",
            {"project_id": self.project.id, "file": upload},
            format="multipart",
        )

        self.assertEqual(response.status_code, 201)
        job = IngestionJob.objects.get()
        item = IngestionItem.objects.get()
        self.assertEqual(job.source_type, IngestionJob.SOURCE_ZIP_UPLOAD)
        self.assertTrue(item.raw_path.endswith("sample.zip"))

    def test_archive_check_uses_exact_archive_filename(self):
        ImageryRecord.objects.create(
            id="archive-check-image",
            scene_key="archive-check-scene",
            identity_hash="a" * 64,
            stac_id="archive-check-scene",
            source_name="different-inner-product",
            archive_filename="scene-A.7z",
            first_uploaded_by=self.user,
        )

        exists = self.client.get("/api/ingestion/archives/check", {"filename": "scene-A.7z"})
        different = self.client.get("/api/ingestion/archives/check", {"filename": "scene-B.7z"})

        self.assertEqual(exists.status_code, 200)
        self.assertTrue(exists.data["exists"])
        self.assertEqual(different.status_code, 200)
        self.assertFalse(different.data["exists"])
