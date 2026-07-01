from typing import Any

from django.conf import settings

from permyt.exceptions import InvalidInputError, InvalidScopeError
from rest_framework.exceptions import ValidationError as DRFValidationError

from .catalogue import (
    SCOPES,
    SCOPES_BY_REFERENCE,
    VALID_ACTIONS,
    ScopeDescriptor,
)


class GovernmentScopes:
    """Static scope catalogue for the Government provider.

    Backed by ``catalogue.SCOPES`` — a tuple of ``ScopeDescriptor`` records.
    Each scope reference is ``<slug>.<action>`` where action is ``read`` for
    direct reads or ``check`` for predicate verifications.
    """

    @staticmethod
    def _parse_reference(reference: str) -> tuple[str, str]:
        """Split a scope reference like ``name.read`` into ``(slug, action)``."""
        parts = reference.rsplit(".", 1)
        if len(parts) != 2 or parts[1] not in VALID_ACTIONS:
            raise InvalidScopeError(f"Scope '{reference}' is not available.")
        return parts[0], parts[1]

    def _get_descriptor(self, reference: str) -> ScopeDescriptor:
        try:
            return SCOPES_BY_REFERENCE[reference]
        except KeyError as exc:
            raise InvalidScopeError(f"Scope '{reference}' is not available.") from exc

    def get_available_scopes(self) -> list[str]:
        """Return all valid scope references."""
        return [d.reference for d in SCOPES]

    def get_input_fields(self, reference: str) -> dict[str, str]:
        """Return the input field definitions for a scope (empty dict for reads)."""
        desc = self._get_descriptor(reference)
        if not desc.input_serializer:
            return {}
        return {
            name: (field.help_text or "") for name, field in desc.input_serializer().fields.items()
        }

    def _get_serializer_cls(self, reference: str):
        return self._get_descriptor(reference).input_serializer

    def validate_params(self, reference: str, params: dict, locked: dict | None = None) -> dict:
        """Validate request-time inputs, enforcing locked values from the token.

        For predicate scopes (``.check``) the broker MUST lock all inputs at
        approval time; an empty ``locked`` for a predicate is rejected
        (fail-closed — identity data should never accept unlocked inputs).
        """
        ser_cls = self._get_serializer_cls(reference)
        if not ser_cls:
            return dict(params or {})

        _, action = self._parse_reference(reference)
        if action == "check" and not locked:
            raise InvalidInputError(
                f"Scope '{reference}' requires broker-locked inputs but none were provided."
            )

        serializer = ser_cls(data=params or {}, locked_data=locked)
        try:
            serializer.is_valid(raise_exception=True)
        except DRFValidationError as exc:
            raise InvalidInputError(str(exc.detail)) from exc
        return dict(serializer.validated_data)

    def validate_locked(self, reference: str, locked: dict) -> dict:
        """Canonicalize locked inputs at token-storage time."""
        ser_cls = self._get_serializer_cls(reference)
        if not ser_cls:
            return dict(locked or {})
        serializer = ser_cls(data=locked or {}, only_lock=True)
        try:
            serializer.is_valid(raise_exception=True)
        except DRFValidationError as exc:
            raise InvalidInputError(str(exc.detail)) from exc
        return dict(serializer.validated_data)

    def execute(self, user, reference: str, params: dict) -> dict:
        """Run the scope's executor against the user's profile.

        Guards profile type: a business scope must not be served from a person
        record (and vice-versa), even though both connect to the same service.
        """
        desc = self._get_descriptor(reference)
        record_type = "business" if getattr(user, "is_business", False) else "person"
        if desc.profile_type != record_type:
            raise InvalidScopeError(
                f"Scope '{reference}' is not available for a {record_type} record."
            )
        return desc.executor(user, params or {})

    @classmethod
    def get_endpoint(cls, reference: str) -> dict[str, Any]:
        """Build a ``ServiceCallEndpoint`` dict for a scope reference."""
        slug, action = cls._parse_reference(reference)
        try:
            desc = SCOPES_BY_REFERENCE[reference]
        except KeyError as exc:
            raise InvalidScopeError(f"Scope '{reference}' is not available.") from exc
        input_fields = (
            {
                name: (field.help_text or "")
                for name, field in desc.input_serializer().fields.items()
            }
            if desc.input_serializer
            else None
        )
        return {
            "url": f"{settings.BASE_URL}/rest/{slug}/{action}/",
            "description": desc.description,
            "input_fields": input_fields,
        }


def sync_scopes_to_broker():
    """Push the static scope catalogue to the PERMYT broker."""
    from app.core.requests.client import PermytClient  # pylint: disable=import-outside-toplevel

    scope_definitions = []
    for desc in SCOPES:
        if desc.input_serializer:
            inputs = [
                {"name": name, "description": (field.help_text or "")}
                for name, field in desc.input_serializer().fields.items()
            ]
        else:
            inputs = []
        scope_definitions.append(
            {
                "reference": desc.reference,
                "name": desc.name,
                "description": desc.description,
                "inputs": inputs,
                "default_consent_mode": desc.default_consent_mode,
                "high_sensitivity": desc.high_sensitivity,
            }
        )

    client = PermytClient()
    return client.update_scopes(scope_definitions)
