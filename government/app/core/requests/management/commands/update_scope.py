"""Push the static Government scope catalogue to the PERMYT broker.

Usage::

    python manage.py update_scope

Run once after deploy and any time ``app/core/requests/scopes/catalogue.py`` changes.
"""

from django.core.management.base import BaseCommand

from app.core.requests.scopes.utils import sync_scopes_to_broker


class Command(BaseCommand):
    help = "Push the static Government scope catalogue to the PERMYT broker."

    def handle(self, *args, **options):
        try:
            response = sync_scopes_to_broker()
        except Exception as exc:  # pylint: disable=broad-exception-caught
            self.stderr.write(self.style.ERROR(f"Failed to update scopes: {exc}"))
            raise

        self.stdout.write(self.style.SUCCESS("Scopes updated successfully."))
        if response is not None:
            self.stdout.write(str(response))
