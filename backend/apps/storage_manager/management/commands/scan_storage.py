from uuid import UUID

from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth import get_user_model

from apps.storage_manager.models import StorageEndpoint, StorageScanJob
from apps.storage_manager.services import create_scan_job


class Command(BaseCommand):
    help = "Scan a registered local/NAS storage endpoint and index relative objects."

    def add_arguments(self, parser):
        parser.add_argument("endpoint_id", type=UUID)
        parser.add_argument("--mode", choices=[choice[0] for choice in StorageScanJob.MODE_CHOICES], default=StorageScanJob.MODE_INCREMENTAL)
        parser.add_argument("--prefix", default="")
        parser.add_argument("--username", default="admin")

    def handle(self, *args, **options):
        endpoint = StorageEndpoint.objects.filter(pk=options["endpoint_id"]).first()
        if endpoint is None:
            raise CommandError("Storage endpoint not found.")
        user = get_user_model().objects.filter(username=options["username"]).first()
        if user is None or not (user.is_staff or user.is_superuser):
            raise CommandError("The command user must be an administrator.")
        job = create_scan_job(endpoint=endpoint, user=user, mode=options["mode"], prefix=options["prefix"])
        if job.status == StorageScanJob.STATUS_FAILED:
            raise CommandError(job.error_message or "Storage scan failed.")
        self.stdout.write(self.style.SUCCESS(
            f"Scan {job.id} completed: files={job.files_scanned}, scenes={job.scenes_found}, "
            f"new={job.new_count}, changed={job.changed_count}, missing={job.missing_count}, "
            f"unchanged={job.unchanged_count}."
        ))
