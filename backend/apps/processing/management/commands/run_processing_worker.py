import time

from django.core.management.base import BaseCommand

from apps.processing.exceptions import ProcessingError
from apps.processing.services import claim_next_job, process_job


class Command(BaseCommand):
    help = "Process pending raster processing jobs."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=float, default=2.0)

    def handle(self, *args, **options):
        while True:
            job = claim_next_job()
            if job:
                try:
                    process_job(job)
                    self.stdout.write(f"processed_processing_job={job.id}")
                except ProcessingError as exc:
                    self.stderr.write(f"failed_processing_job={job.id} error={exc}")
                except Exception as exc:  # noqa: BLE001
                    self.stderr.write(f"failed_processing_job={job.id} error={exc}")
                continue
            if options["once"]:
                return
            time.sleep(options["interval"])
