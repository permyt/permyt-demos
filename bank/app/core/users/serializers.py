from rest_framework import serializers

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


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """Partial-update serializer for the editable account fields shown in the
    bank dashboard. Only ``full_name`` is editable — IBAN, balance, and
    currency are immutable from the UI."""

    class Meta:
        model = User
        fields = ("full_name",)
        extra_kwargs = {"full_name": {"required": False}}
