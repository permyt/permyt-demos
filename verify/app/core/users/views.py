from app.mixins.viewsets import AppModelViewSet

from .models import User


class UserViewSet(AppModelViewSet):
    """Read-only stub — exists only because the URL conf may import it."""

    model = User
    CAN_CREATE = False
    CAN_DELETE = False
