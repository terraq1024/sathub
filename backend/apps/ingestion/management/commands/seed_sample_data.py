"""Ingest the bundled sample scenes and create a demo account."""
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand

from apps.ingestion.services import create_archive_upload_job, process_job


class Command(BaseCommand):
    help = "Ingest the bundled sample scenes into a fresh installation and create a demo account."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")
        parser.add_argument("--password", default="demo1234")
        parser.add_argument(
            "--sample-dir",
            default=str(Path(settings.ROOT_DIR) / "sample-data"),
            help="Directory containing sample GeoTIFF scenes.",
        )

    def handle(self, *args, **options):
        sample_dir = Path(options["sample_dir"])
        scenes = sorted(sample_dir.glob("*.tif")) + sorted(sample_dir.glob("*.tiff"))
        if not scenes:
            self.stderr.write(self.style.ERROR(f"No sample scenes (*.tif) found in {sample_dir}"))
            return

        user_model = get_user_model()
        user, created = user_model.objects.get_or_create(
            username=options["username"],
            defaults={"is_staff": True},
        )
        if created:
            user.set_password(options["password"])
            user.save(update_fields=["password"])
        elif user.password.startswith("!"):
            # get_or_create produced an unusable password (existing username).
            user.set_password(options["password"])
            user.save(update_fields=["password"])

        with tempfile.TemporaryDirectory() as tmp:
            archive_path = Path(tmp) / "airmap-samples.zip"
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as bundle:
                for scene in scenes:
                    bundle.write(scene, arcname=scene.name)
            job = create_archive_upload_job(
                user=user,
                project_id=None,
                uploaded_file=SimpleUploadedFile(archive_path.name, archive_path.read_bytes()),
            )
            process_job(job)

        self.stdout.write(self.style.SUCCESS(
            f"Seeded {job.success_count} sample scene(s) "
            f"(skipped {job.skipped_count}, failed {job.failed_count}). "
            f"Log in with {options['username']} / {options['password']}."
        ))
