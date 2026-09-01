import time

from django.core.management.base import BaseCommand

from apps.publishing.services import claim_publish_job, process_publish_job


class Command(BaseCommand):
    help = "Process imagery service publication jobs."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--poll-interval", type=float, default=2.0)

    def handle(self, *args, **options):
        while True:
            job = claim_publish_job()
            if job:
                process_publish_job(job)
                self.stdout.write(f"processed_service_job={job.id}")
            elif options["once"]:
                return
            else:
                time.sleep(options["poll_interval"])
