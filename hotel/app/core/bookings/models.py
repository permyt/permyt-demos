from decimal import Decimal

from django.conf import settings
from django.contrib.sessions.models import Session
from django.db.models import TextChoices

from app import models


class BookingStatus(TextChoices):
    PENDING = "pending", "Pending"
    IDENTITY_REQUESTED = "identity_requested", "Identity requested"
    IDENTITY_FILLED = "identity_filled", "Identity filled"
    PAYMENT_REQUESTED = "payment_requested", "Payment requested"
    PAID = "paid", "Paid"
    FAILED = "failed", "Failed"


class Booking(models.AppModel):
    """
    A hotel check-in session.

    Keyed on the Django session_key (anonymous — no user account). Holds the
    PERMYT user id (set after QR scan), the form fields auto-filled from the
    identity provider, the chosen number of nights, and payment state.
    """

    WEBSOCKET_NOTIFICATIONS_ENABLED = False  # we push custom WS messages, not model saves

    session_key = models.CharField(max_length=40, unique=True, db_index=True)
    permyt_user_id = models.UUIDField(null=True, blank=True, db_index=True)
    status = models.CharField(
        max_length=32,
        choices=BookingStatus.choices,
        default=BookingStatus.PENDING,
    )

    form_data = models.EncryptedJSONField(default=dict)

    nights = models.PositiveSmallIntegerField(default=1)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="EUR")

    identity_request_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    payment_request_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)
    payment_reference = models.CharField(max_length=64, null=True, blank=True)
    failure_reason = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"Booking({self.session_key[:8]}…, {self.status})"

    def compute_total(self) -> Decimal:
        rate = Decimal(settings.HOTEL_NIGHTLY_RATE)
        total = rate * Decimal(self.nights)
        return total.quantize(Decimal("0.01"))

    def set_status(self, status: str, *, save: bool = True, **extra) -> None:
        self.status = status
        for field, value in extra.items():
            setattr(self, field, value)
        if save:
            self.save()


class LoginToken(models.AppModel):
    """
    Short-lived token binding a QR connect-token payload to a session/booking.

    Created when the hotel page renders. When the broker's ``user_connect``
    callback arrives, the client looks up this row, marks it scanned, and
    attaches the resolved ``permyt_user_id`` to the Booking.
    """

    WEBSOCKET_NOTIFICATIONS_ENABLED = False
    DELETE_AFTER = 5 * 60  # minutes

    token = models.CharField(max_length=2048, unique=True)
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="login_tokens")
    booking = models.ForeignKey(
        Booking, on_delete=models.CASCADE, related_name="login_tokens", null=True, blank=True
    )
    scanned = models.BooleanField(default=False)
