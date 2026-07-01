from rest_framework import serializers

from app.mixins.serializers import AppModelSerializer

from .models import CompanyKB, LoginToken, User


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


class CompanyKBUpdateSerializer(serializers.ModelSerializer):
    """Partial-update serializer for the company knowledge base shown in the
    dashboard. ``products`` arrives as a newline-separated textarea string and
    is stored as a JSON list.

    Identity fields (``name`` / ``registration_number`` / ``registered_address``
    / ``country``) are Gov.ID-sourced and intentionally NOT editable — only the
    company's own knowledge base is."""

    products = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = CompanyKB
        fields = ("business_plan", "financials_summary", "products", "narrative")
        extra_kwargs = {
            "business_plan": {"required": False},
            "financials_summary": {"required": False},
            "narrative": {"required": False},
        }

    def validate_products(self, value: str) -> list:
        return [line.strip() for line in (value or "").splitlines() if line.strip()]
