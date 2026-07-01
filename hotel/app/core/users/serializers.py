from app.mixins.serializers import AppModelSerializer

from .models import User


class UserSerializer(AppModelSerializer):
    """Read-only — the hotel demo never exposes user accounts."""

    class Meta:
        model = User
        fields = ("email",)
        read_only_fields = fields
