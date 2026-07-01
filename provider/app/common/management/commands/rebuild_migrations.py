import subprocess

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand

from .migrate_all import Command as MigrateAllCommand


class Command(BaseCommand):
    help = "Rebuild migrations from scratch."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="If set, the command will not try to make migrations.",
        )

        parser.add_argument(
            "--skip-migrations",
            action="store_true",
            help="If set, the command will not try to migrate database.",
        )

    def handle(self, *args, **options):
        """Rebuild migrations from scratch."""

        # Make sure there are no migrations applied that is not in the database
        try:
            call_command("makemigrations", ["users"], interactive=True)
            call_command("makemigrations", interactive=True)
            if not options.get("skip_migrations"):
                MigrateAllCommand().handle()
        except Exception as e:  # pylint: disable=broad-except
            if not options.get("force"):
                raise e from e

        # Delete existing migrations
        path = settings.BASE_DIR / "app"
        delete_migrations_command = ["find", ".", "-name", "00*.py", "-delete"]
        with subprocess.Popen(delete_migrations_command, cwd=path) as p:
            p.wait()

        # Generate new migrations
        call_command("makemigrations", ["users"], interactive=True)
        call_command("makemigrations", interactive=True)
