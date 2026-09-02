import time

from django.core.management.base import BaseCommand

from apps.ingestion.services import run_pending_jobs


class Command(BaseCommand):
    help = "Poll and process pending ingestion jobs."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process pending jobs once and exit.")
        parser.add_argument("--sleep", type=int, default=10, help="Polling interval in seconds.")
        parser.add_argument("--limit", type=int, default=None, help="Maximum jobs per polling cycle.")

    def handle(self, *args, **options):
        while True:
            processed = run_pending_jobs(limit=options["limit"])
            self.stdout.write(f"processed_jobs={processed}")
            if options["once"]:
                return
            time.sleep(options["sleep"])
