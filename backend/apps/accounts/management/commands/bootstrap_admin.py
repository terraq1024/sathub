"""Create the first admin account.

Three modes, in priority order:
1. SATHUB_ADMIN_PASSWORD is set  -> create (or skip if an admin exists)
   using SATHUB_ADMIN_USERNAME (default "admin"). Non-interactive, used
   by the Docker entrypoint.
2. No env vars and no admin exists -> interactive prompt for username
   and password (same UX as Django's createsuperuser).
3. An admin already exists and no env vars are set -> skipped.
"""
import getpass
import os

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the first admin account (env-driven or interactive) when none exists."

    def handle(self, *args, **options):
        username = os.environ.get("SATHUB_ADMIN_USERNAME", "admin")
        password = os.environ.get("SATHUB_ADMIN_PASSWORD", "")

        # Env-driven mode (Docker entrypoint, scripted installs).
        if password:
            if User.objects.filter(is_staff=True).exists():
                self.stdout.write("bootstrap_admin: admin already exists; skipped.")
                return
            User.objects.create_superuser(username=username, password=password)
            self.stdout.write(self.style.SUCCESS(f"bootstrap_admin: created admin '{username}'."))
            return

        # Interactive mode: only ask when there is no admin to log in with,
        # otherwise a plain `bootstrap_admin` would nag every run.
        if User.objects.filter(is_staff=True).exists():
            self.stdout.write("bootstrap_admin: admin already exists; skipped.")
            return

        self.stdout.write("No admin account exists yet. Create one now")
        self.stdout.write("(this account can manage users and system settings):\n")
        while True:
            username = input("Username [admin]: ").strip() or "admin"
            if not User.objects.filter(username__iexact=username).exists():
                break
            self.stdout.write(self.style.ERROR(f"Username '{username}' is already taken."))
        while True:
            password = getpass.getpass("Password (min 8 chars, not purely numeric): ")
            if len(password) < 8:
                self.stdout.write(self.style.ERROR("Password is too short."))
                continue
            if password.isdigit():
                self.stdout.write(self.style.ERROR("Password cannot be purely numeric."))
                continue
            password2 = getpass.getpass("Password (again): ")
            if password != password2:
                self.stdout.write(self.style.ERROR("Passwords do not match."))
                continue
            break

        User.objects.create_superuser(username=username, password=password)
        self.stdout.write(self.style.SUCCESS(
            f"bootstrap_admin: admin '{username}' created. Log in at /admin or on the login page."
        ))
