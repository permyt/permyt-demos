"""Wipe the demo back to a clean slate.

Deletes all local Log rows and Users. Intended for the sandbox demo only.

    python manage.py reset_demo
    python manage.py reset_demo --keep-superusers   # keep Django admin logins
"""

from django.core.management.base import BaseCommand

from app.core.logs.models import Log
from app.core.users.models import User


class Command(BaseCommand):
    help = "Delete all logs and users (demo reset)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-superusers",
            action="store_true",
            help="Do not delete superusers (keeps Django admin access).",
        )

    def handle(self, *args, **options):
        log_count = Log.objects.all().count()
        Log.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {log_count} log row(s)."))

        users = User.objects.all()
        if options["keep_superusers"]:
            users = users.filter(is_superuser=False)
        user_count = users.count()
        users.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {user_count} user(s)."))
