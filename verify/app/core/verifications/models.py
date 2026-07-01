from django.contrib.sessions.models import Session
from django.db.models import TextChoices

from app import models


class VerificationStatus(TextChoices):
    PENDING = "pending", "Pending"
    SCANNED = "scanned", "Scanned"
    AWAITING = "awaiting", "Awaiting approval"
    VERIFYING = "verifying", "Verifying"
    VERIFIED = "verified", "Verified"
    FAILED = "failed", "Failed"


class Verification(models.AppModel):
    """
    An age-verification session.

    Keyed on the Django session_key (anonymous — no user account). Holds the
    PERMYT user id (set after QR scan), the broker request id, the minimum age
    being checked (default 18), and the boolean result returned by the
    government provider.
    """

    WEBSOCKET_NOTIFICATIONS_ENABLED = False  # we push custom WS messages, not model saves

    session_key = models.CharField(max_length=40, unique=True, db_index=True)
    permyt_user_id = models.UUIDField(null=True, blank=True, db_index=True)
    status = models.CharField(
        max_length=32,
        choices=VerificationStatus.choices,
        default=VerificationStatus.PENDING,
    )

    min_age = models.PositiveSmallIntegerField(default=18)
    is_older = models.BooleanField(null=True, blank=True)

    request_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    failure_reason = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"Verification({self.session_key[:8]}…, {self.status})"

    def set_status(self, status: str, *, save: bool = True, **extra) -> None:
        self.status = status
        for field, value in extra.items():
            setattr(self, field, value)
        if save:
            self.save()


class LoginToken(models.AppModel):
    """
    Short-lived token binding a QR connect-token payload to a session/verification.

    Created when the verify page renders. When the broker's ``user_connect``
    callback arrives, the client looks up this row, marks it scanned, and
    attaches the resolved ``permyt_user_id`` to the Verification.
    """

    WEBSOCKET_NOTIFICATIONS_ENABLED = False
    DELETE_AFTER = 5 * 60  # minutes

    token = models.CharField(max_length=2048, unique=True)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="login_tokens")
    verification = models.ForeignKey(
        Verification,
        on_delete=models.CASCADE,
        related_name="login_tokens",
        null=True,
        blank=True,
    )
    scanned = models.BooleanField(default=False)
