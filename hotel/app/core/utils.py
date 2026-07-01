from datetime import timedelta

from django.utils import timezone

from app.core.bookings.models import Booking, LoginToken
from app.core.logs.models import Log
from app.core.requests.models import Nonce


class CleanUpData:
    """
    Utility class to clean up old nonces, login tokens, and abandoned
    bookings/logs. Run periodically via a scheduled task.
    """

    BOOKING_DELETE_AFTER = 60 * 24  # 24h, in minutes

    def clean(self):
        now = timezone.now()
        for model in (Nonce, LoginToken, Log):
            until = now - timedelta(minutes=model.DELETE_AFTER)
            model.objects.filter(created_at__lt=until).delete()

        # Drop abandoned bookings (older than 24h, not paid).
        until = now - timedelta(minutes=self.BOOKING_DELETE_AFTER)
        Booking.objects.filter(created_at__lt=until).exclude(status="paid").delete()
