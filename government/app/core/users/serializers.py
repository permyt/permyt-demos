import re

from rest_framework import serializers

from app.mixins.serializers import AppModelSerializer

from .models import BusinessProfile, Shareholder, User, LoginToken

PHONE_E164_RE = re.compile(r"^\+\d{6,15}$")


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
    """Partial-update serializer for the citizen profile fields shown in the dashboard."""

    class Meta:
        model = User
        fields = (
            "full_name",
            "birthdate",
            "address",
            "country",
            "vat",
            "phone",
            "email",
            "tax_id",
            "passport_number",
            "social_security_number",
            "citizen_card_number",
        )
        extra_kwargs = {field: {"required": False} for field in fields}

    def validate_country(self, value: str) -> str:
        value = (value or "").strip().upper()
        if value and not re.match(r"^[A-Z]{2}$", value):
            raise serializers.ValidationError("country must be a 2-letter ISO 3166-1 alpha-2 code.")
        return value

    def validate_phone(self, value: str) -> str:
        value = (value or "").strip()
        if value and not PHONE_E164_RE.match(value):
            raise serializers.ValidationError("phone must be E.164 (e.g. +14155551234).")
        return value


class ShareholderSerializer(serializers.ModelSerializer):
    """Validate a single beneficial owner / officer row from the dashboard editor."""

    class Meta:
        model = Shareholder
        fields = (
            "first_name",
            "last_name",
            "birthdate",
            "address",
            "country",
            "id_number",
            "ownership_percent",
            "title",
            "is_representative",
            "is_director",
        )
        extra_kwargs = {field: {"required": False} for field in fields}

    def validate_country(self, value: str) -> str:
        value = (value or "").strip().upper()
        if value and not re.match(r"^[A-Z]{2}$", value):
            raise serializers.ValidationError("country must be a 2-letter ISO 3166-1 alpha-2 code.")
        return value


class BusinessProfileUpdateSerializer(serializers.ModelSerializer):
    """Partial-update serializer for the organisation record shown in the dashboard."""

    class Meta:
        model = BusinessProfile
        fields = (
            "legal_name",
            "registration_number",
            "tax_id",
            "incorporation_date",
            "registered_address",
            "country",
            "structure",
            "mcc",
            "website",
        )
        extra_kwargs = {field: {"required": False} for field in fields}

    def validate_country(self, value: str) -> str:
        value = (value or "").strip().upper()
        if value and not re.match(r"^[A-Z]{2}$", value):
            raise serializers.ValidationError("country must be a 2-letter ISO 3166-1 alpha-2 code.")
        return value
