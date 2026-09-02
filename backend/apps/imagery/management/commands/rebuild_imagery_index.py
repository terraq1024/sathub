from django.core.management.base import BaseCommand, CommandError

from apps.imagery.models import ImageryRecord
from apps.imagery.services import rebuild_imagery_projection


class Command(BaseCommand):
    help = "Rebuild the DuckDB imagery index and regenerate every STAC Item from Django data."

    def handle(self, *args, **options):
        total = ImageryRecord.objects.count()
        self.stdout.write(f"Rebuilding {total} imagery projections...")
        failures = rebuild_imagery_projection()
        if failures:
            details = "; ".join(f"{image_id}: {message}" for image_id, message in failures[:10])
            raise CommandError(f"Rebuild completed with {len(failures)} failure(s): {details}")
        self.stdout.write(self.style.SUCCESS(f"Rebuilt {total} imagery projections."))
