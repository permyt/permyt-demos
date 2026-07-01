"""No-op scope publish.

This service does not publish a static scope catalogue (it is a requester, or a
provider whose scopes are synced dynamically). The command exists so every demo
exposes the same ``update_scope`` command and the shared deploy script can call
it unconditionally.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "No static scope catalogue to publish for this service (no-op)."

    def handle(self, *args, **options):
        self.stdout.write("No scopes to update for this service.")
