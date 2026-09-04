"""Create the first admin account from environment variables.

Runs on every backend container start (Dockerfile CMD). Idempotent:
only acts when SATHUB_ADMIN_PASSWORD is set AND no admin exists yet.
"""
import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the first admin from SATHUB_ADMIN_USERNAME/PASSWORD when no admin exists."

    def handle(self, *args, **options):
        username = os.environ.get("SATHUB_ADMIN_USERNAME", "admin")
        password = os.environ.get("SATHUB_ADMIN_PASSWORD", "")
        if not password:
            self.stdout.write("bootstrap_admin: SATHUB_ADMIN_PASSWORD not set; skipped.")
            return
        if User.objects.filter(is_staff=True).exists():
            self.stdout.write("bootstrap_admin: admin already exists; skipped.")
            return
        User.objects.create_superuser(username=username, password=password)
        self.stdout.write(self.style.SUCCESS(f"bootstrap_admin: created admin '{username}'."))
