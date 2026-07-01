"""Wipe the demo back to a clean slate.

Deletes every Stripe connected (merchant) account this platform created, then
all local Log rows and Users. Intended for the sandbox demo only — guarded to
refuse a live Stripe key unless ``--force`` is passed.

    python manage.py reset_demo
    python manage.py reset_demo --keep-superusers   # keep Django admin logins
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from app.core.logs.models import Log
from app.core.users.models import User


class Command(BaseCommand):
    help = "Delete all Stripe connected accounts, logs and users (demo reset)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--keep-superusers",
            action="store_true",
            help="Do not delete superusers (keeps Django admin access).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Allow running against a non-test Stripe key.",
        )

    def handle(self, *args, **options):
        self._reset_stripe(force=options["force"])

        log_count = Log.objects.all().count()
        Log.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {log_count} log row(s)."))

        users = User.objects.all()
        if options["keep_superusers"]:
            users = users.filter(is_superuser=False)
        user_count = users.count()
        users.delete()
        self.stdout.write(self.style.SUCCESS(f"Deleted {user_count} user(s)."))

    def _reset_stripe(self, force: bool) -> None:
        """Delete every connected account the platform can delete."""
        key = settings.STRIPE_SECRET_KEY
        if not key:
            self.stdout.write(self.style.WARNING("No STRIPE_SECRET_KEY — skipping Stripe."))
            return
        if not key.startswith("sk_test") and not force:
            raise CommandError(
                "Refusing to delete connected accounts on a non-test Stripe key. "
                "Re-run with --force if you really mean it."
            )

        import stripe  # noqa: PLC0415

        stripe.api_key = key
        client = stripe.StripeClient(key)
        deleted = failed = 0
        for account in stripe.Account.list(limit=100).auto_paging_iter():
            try:
                stripe.Account.delete(account.id)
                deleted += 1
            except Exception as v1_exc:  # noqa: BLE001
                # Accounts linked to a v2 core account can't be deleted via v1;
                # they must be closed through the v2 close endpoint, which
                # requires the account's exact applied configurations.
                try:
                    self._close_v2(client, account.id)
                    deleted += 1
                except Exception as v2_exc:  # noqa: BLE001
                    failed += 1
                    self.stderr.write(f"Could not delete {account.id}: {v1_exc} / {v2_exc}")

        msg = f"Deleted {deleted} Stripe connected account(s)."
        if failed:
            msg += f" {failed} could not be deleted."
        self.stdout.write(self.style.SUCCESS(msg))

    @staticmethod
    def _close_v2(client, account_id: str) -> None:
        """Close a v2-linked account, passing its exact applied configurations
        (Stripe rejects the close unless every applied configuration is named).
        """
        account = client.v2.core.accounts.retrieve(account_id)
        configs = list(getattr(account, "applied_configurations", None) or [])
        if not configs:
            configs = ["customer", "merchant", "recipient"]
        client.v2.core.accounts.close(account_id, {"applied_configurations": configs})
