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


class CompanyAskSerializer(ScopeSerializer):  # pylint: disable=abstract-method
    """Input for ``company.ask`` — the open-ended question, locked at approval."""

    question = serializers.CharField(
        max_length=2000,
        required=True,
        help_text="The question to ask the company's agent.",
    )

    class Meta:
        locked_fields = ("question",)
