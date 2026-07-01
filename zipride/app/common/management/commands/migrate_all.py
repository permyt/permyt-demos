import logging

from django.conf import settings
from django.core.management.base import BaseCommand
from django.core.management import call_command

logger = logging.getLogger("console")


class Command(BaseCommand):
    help = "Migrate all databases, default and history"

    def handle(self, *args, **options):
        for db in settings.DATABASES:
            logger.info(f"\n>>> Migrating database: {db}...\n")
            call_command("migrate", ["--database", db], interactive=True)
