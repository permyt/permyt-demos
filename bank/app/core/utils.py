from datetime import timedelta

from django.utils import timezone

from app.core.logs.models import Log
from app.core.requests.models import Nonce, RequestToken
from app.core.users.models import LoginToken


class CleanUpData:
    """
    Utility class to clean up old nonces and other temporary data from the database.
    This should be run periodically via a scheduled task.
    """

    def clean(self):
        """
        Run cleanup tasks.
        """
        now = timezone.now()
        for model in (Nonce, RequestToken, LoginToken, Log):
            until = now - timedelta(minutes=model.DELETE_AFTER)
            model.objects.filter(created_at__lt=until).delete()
