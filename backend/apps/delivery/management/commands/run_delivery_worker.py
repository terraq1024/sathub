import time
from django.core.management.base import BaseCommand
from apps.delivery.services import process_pending


class Command(BaseCommand):
    help = "Process pending delivery export jobs."
    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true")
        parser.add_argument("--interval", type=float, default=2)
    def handle(self, *args, **options):
        while True:
            count = process_pending()
            if options["once"]: return
            if not count: time.sleep(options["interval"])
