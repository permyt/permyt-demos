from app.mixins.serializers import AppModelSerializer

from .models import User, LoginToken


class UserSerializer(AppModelSerializer):
    """Serializer for the User model — read-only profile view."""

    class Meta:
        model = User
        fields = ("email", "permyt_user_id", "is_account_manager")
        read_only_fields = ("permyt_user_id", "is_account_manager")
        immutable_fields = ("permyt_user_id",)


class LoginTokenSerializer(AppModelSerializer):
    """Serializer for the LoginToken model — used for one-time login links."""

    class Meta:
        model = LoginToken
        fields = ("token", "created_at")
        read_only_fields = ("created_at",)
        immutable_fields = ("token",)
