import logging
import shlex
import subprocess

from django.core.management.base import BaseCommand
from django.utils import autoreload

logger = logging.getLogger("console")


NODE = "demo-provider"


def restart_celery():
    # Unique -n node name so pkill only targets THIS project's worker. Without
    # it, sibling repos that ship the same celery command (broker, demo
    # requester, etc.) get killed too on autoreload.
    celery_worker_cmd = f"celery -A settings worker -n {NODE}@%h -P threads --concurrency=4 -B"
    subprocess.call(["pkill", "-f", "--", f"-n {NODE}@"])
    subprocess.call(shlex.split(f"{celery_worker_cmd} --loglevel=info"))


class Command(BaseCommand):
    def handle(self, *args, **options):
        logger.debug("Starting celery worker with autoreload...")
        autoreload.run_with_reloader(restart_celery)
