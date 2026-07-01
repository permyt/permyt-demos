from rest_framework import serializers

from app.mixins.serializers import AppModelSerializer

from .models import User, LoginToken


class UserSerializer(AppModelSerializer):
    """Serializer for the User model — read-only screening view."""

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


class ScreeningUpdateSerializer(serializers.ModelSerializer):
    """Partial-update serializer for the four screening outcomes.

    Editable from the dashboard so a subject can be flagged to demo denials.
    """

    class Meta:
        model = User
        fields = (
            "sanctions_match",
            "pep",
            "adverse_media",
            "self_excluded",
        )
        extra_kwargs = {field: {"required": False} for field in fields}
