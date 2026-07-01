"""Seed the Sentinel Screening provider with demo subjects.

Creates a couple of unlinked screening records (no ``permyt_user_id``) so the
demo has data to inspect:

  * A clear subject (all four checks False).
  * A flagged subject (sanctions + adverse media) to demonstrate denials.

Idempotent — re-running updates the existing records in place. Connect a
record by scanning the login QR with the PERMYT app.

Usage::

    python manage.py seed_demo
"""

from django.core.management.base import BaseCommand

from app.core.users.models import User


class Command(BaseCommand):
    help = "Seed the Sentinel Screening demo subjects (one clear, one flagged)."

    def handle(self, *args, **options):
        clear = self._seed_subject(
            username="subject-clear",
            email="clear@subjects.sentinel.permyt.io",
            sanctions_match=False,
            pep=False,
            adverse_media=False,
            self_excluded=False,
        )
        flagged = self._seed_subject(
            username="subject-flagged",
            email="flagged@subjects.sentinel.permyt.io",
            sanctions_match=True,
            pep=False,
            adverse_media=True,
            self_excluded=False,
        )
        self.stdout.write(self.style.SUCCESS("Seeded Sentinel screening subjects."))
        self.stdout.write(f"  Clear subject id:   {clear.id}")
        self.stdout.write(f"  Flagged subject id: {flagged.id}")

    def _seed_subject(self, *, username: str, email: str, **outcomes) -> User:
        user, _ = User.objects.get_or_create(
            username=username,
            defaults={"email": email, **outcomes},
        )
        user.email = email
        for field, value in outcomes.items():
            setattr(user, field, value)
        user.save()
        return user
