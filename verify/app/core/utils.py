from datetime import timedelta

from django.utils import timezone

from app.core.logs.models import Log
from app.core.requests.models import Nonce
from app.core.verifications.models import LoginToken, Verification, VerificationStatus


class CleanUpData:
    """
    Utility class to clean up old nonces, login tokens, and abandoned
    verifications/logs. Run periodically via a scheduled task.
    """

    VERIFICATION_DELETE_AFTER = 60 * 24  # 24h, in minutes

    def clean(self):
        now = timezone.now()
        for model in (Nonce, LoginToken, Log):
            until = now - timedelta(minutes=model.DELETE_AFTER)
            model.objects.filter(created_at__lt=until).delete()

        # Drop abandoned verifications (older than 24h, not verified).
        until = now - timedelta(minutes=self.VERIFICATION_DELETE_AFTER)
        Verification.objects.filter(created_at__lt=until).exclude(
            status=VerificationStatus.VERIFIED
        ).delete()
