import re

from rest_framework import serializers

from permyt.exceptions import InvalidInputError


class ScopeSerializer(serializers.Serializer):  # pylint: disable=abstract-method
    """Base for scope-input serializers.

    ``Meta.locked_fields`` declares the fields that the broker locks at token
    issuance. Two validation modes beyond default DRF behaviour:

    * ``only_lock=True`` — drop every non-locked field, then validate. Used
      by ``store_token`` to canonicalize the locked inputs before persisting.
    * ``locked_data=<dict>`` — full validation, then enforce that every
      locked field matches the canonicalized locked value. Used by
      ``process_request`` to block tampering between approval and execution.
    """

    class Meta:
        locked_fields: tuple[str, ...] = ()

    def __init__(self, *args, only_lock: bool = False, locked_data=None, **kwargs):
        self._only_lock = only_lock
        self._locked_data = locked_data
        super().__init__(*args, **kwargs)
        if only_lock:
            locked = getattr(self.Meta, "locked_fields", ()) or ()
            for name in list(self.fields):
                if name not in locked:
                    self.fields.pop(name)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if self._locked_data is None:
            return attrs
        locked_fields = getattr(self.Meta, "locked_fields", ()) or ()
        if not locked_fields:
            return attrs
        canonical = type(self)(data=self._locked_data, only_lock=True)
        canonical.is_valid(raise_exception=True)
        canonical_data = canonical.validated_data
        for field in locked_fields:
            if attrs.get(field) != canonical_data.get(field):
                raise InvalidInputError(f"{field} does not match the approved value.")
        return attrs


class IsOlderSerializer(ScopeSerializer):  # pylint: disable=abstract-method
    """Input for ``is_older.check`` — minimum age in whole years."""

    min_age = serializers.IntegerField(
        min_value=0,
        max_value=150,
        required=True,
        help_text="Minimum age in whole years to verify against.",
    )

    class Meta:
        locked_fields = ("min_age",)


class IsResidentOfSerializer(ScopeSerializer):  # pylint: disable=abstract-method
    """Input for ``is_resident_of.check`` — ISO 3166-1 alpha-2 country code."""

    country_code = serializers.CharField(
        min_length=2,
        max_length=2,
        required=True,
        help_text="ISO 3166-1 alpha-2 country code (e.g. US, PT).",
    )

    class Meta:
        locked_fields = ("country_code",)

    def validate_country_code(self, value: str) -> str:
        value = (value or "").strip().upper()
        if not re.match(r"^[A-Z]{2}$", value):
            raise serializers.ValidationError(
                "country_code must be a 2-letter ISO 3166-1 alpha-2 code."
            )
        return value


class VatMatchesSerializer(ScopeSerializer):  # pylint: disable=abstract-method
    """Input for ``vat_matches.check`` — VAT number to compare against."""

    value = serializers.CharField(
        max_length=64,
        required=True,
        help_text="VAT number to compare against the citizen's record.",
    )

    class Meta:
        locked_fields = ("value",)


class CompanyIsRegisteredSerializer(ScopeSerializer):  # pylint: disable=abstract-method
    """Input for ``company.is_registered.check`` — registration number to verify."""

    registration_number = serializers.CharField(
        max_length=64,
        required=True,
        help_text="Company registration number to verify against the registry.",
    )

    class Meta:
        locked_fields = ("registration_number",)
