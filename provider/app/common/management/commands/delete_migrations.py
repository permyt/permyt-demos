import subprocess

from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Delete existing migrations."

    def handle(self, *args, **options):
        """Delete existing migrations."""

        path = settings.BASE_DIR / "app"
        delete_migrations_command = ["find", ".", "-name", "00*.py", "-delete"]
        with subprocess.Popen(delete_migrations_command, cwd=path) as p:
            p.wait()
