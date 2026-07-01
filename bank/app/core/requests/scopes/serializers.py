from decimal import Decimal

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


class PaymentSendSerializer(ScopeSerializer):  # pylint: disable=abstract-method
    """Input for ``payment.send``.

    Locked at the broker (the user approves these on their mobile app):

    * ``account`` — beneficiary account / IBAN.
    * ``value`` — amount to transfer.
    * ``currency`` — ISO 4217 currency code.

    Set by the requester at call time (free-form, not locked):

    * ``name`` — beneficiary's display name.
    * ``description`` — payment description / reference shown to the beneficiary.
    """

    account = serializers.CharField(
        max_length=34,
        help_text="Beneficiary account / IBAN (whitespace and dashes are stripped).",
    )
    value = serializers.DecimalField(
        max_digits=14,
        decimal_places=2,
        min_value=Decimal("0.01"),
        help_text="Amount to transfer (in the locked currency).",
    )
    currency = serializers.CharField(
        max_length=3,
        help_text="ISO 4217 currency code (e.g. EUR, GBP, USD).",
    )
    name = serializers.CharField(
        max_length=255,
        allow_blank=True,
        required=False,
        help_text="Beneficiary's display name.",
    )
    description = serializers.CharField(
        max_length=255,
        allow_blank=True,
        required=False,
        help_text="Free-text payment description shown to the beneficiary.",
    )

    class Meta:
        locked_fields = ("account", "value", "currency")

    def validate_account(self, value: str) -> str:
        return (value or "").replace(" ", "").replace("-", "").upper()

    def validate_currency(self, value: str) -> str:
        return (value or "").strip().upper()
