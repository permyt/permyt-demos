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

# Actions whose inputs MUST be locked at the broker (fail-closed). ``ask`` joins
# ``check`` here: the requester's question is locked into the grant at approval.
LOCKED_ACTIONS = ("check", "ask")


class CompanyAgentScopes:
    """Static scope catalogue for the Company-Agent provider.

    Backed by ``catalogue.SCOPES``. References are ``<slug>.<action>`` where
    action is ``read`` (structured KB read) or ``ask`` (open-ended LLM answer).
    """

    @staticmethod
    def _parse_reference(reference: str) -> tuple[str, str]:
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
        return [d.reference for d in SCOPES]

    def get_input_fields(self, reference: str) -> dict[str, str]:
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

        ``ask`` scopes (like predicates) MUST arrive with broker-locked inputs;
        an empty ``locked`` is rejected (fail-closed)."""
        ser_cls = self._get_serializer_cls(reference)
        if not ser_cls:
            return dict(params or {})

        _, action = self._parse_reference(reference)
        if action in LOCKED_ACTIONS and not locked:
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
        desc = self._get_descriptor(reference)
        return desc.executor(user, params or {})

    @classmethod
    def get_endpoint(cls, reference: str) -> dict[str, Any]:
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
