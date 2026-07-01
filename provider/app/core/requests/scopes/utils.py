from typing import Any

from django.conf import settings

from permyt.exceptions import InvalidInputError, InvalidScopeError
from rest_framework.exceptions import ValidationError as DRFValidationError

from app.core.users.models import NoteField, UserFieldValue
from .serializers import NoteWriteSerializer


class NoteVaultScopes:
    """
    Dynamic scope catalogue backed by NoteField records in the database.

    Each NoteField with slug ``X`` yields two scopes: ``X.read`` and ``X.write``.
    Write scopes use NoteWriteSerializer for input validation.
    """

    @staticmethod
    def _all_slugs() -> set[str]:
        """Return the set of all NoteField slugs from the database."""
        return set(NoteField.objects.values_list("slug", flat=True))

    @staticmethod
    def _parse_reference(reference: str) -> tuple[str, str]:
        """Split a scope reference like ``mission_log.read`` into ``(slug, action)``."""
        parts = reference.rsplit(".", 1)
        if len(parts) != 2 or parts[1] not in ("read", "write"):
            raise InvalidScopeError(f"Scope '{reference}' is not available.")
        return parts[0], parts[1]

    def _validate_slug(self, slug: str, reference: str) -> None:
        """Raise ``InvalidScopeError`` if the slug is not a known NoteField."""
        if slug not in self._all_slugs():
            raise InvalidScopeError(f"Scope '{reference}' is not available.")

    # ------------------------------------------------------------------
    # Catalogue queries
    # ------------------------------------------------------------------

    def get_available_scopes(self) -> list[str]:
        """Return all valid scope references derived from current NoteField records."""
        scopes = []
        for slug in sorted(self._all_slugs()):
            scopes.append(f"{slug}.read")
            scopes.append(f"{slug}.write")
        return scopes

    def get_input_fields(self, reference: str) -> dict[str, str]:
        """Return the input field definitions for a scope (empty dict for reads)."""
        ser_cls = self._get_serializer_cls(reference)
        if not ser_cls:
            return {}
        return {name: (field.help_text or "") for name, field in ser_cls().fields.items()}

    # ------------------------------------------------------------------
    # Serializer resolution
    # ------------------------------------------------------------------

    def _get_serializer_cls(self, reference: str):
        """Resolve the DRF serializer class for a scope (None for reads)."""
        slug, action = self._parse_reference(reference)
        self._validate_slug(slug, reference)
        return NoteWriteSerializer if action == "write" else None

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate_params(self, reference: str, params: dict, locked: dict | None = None) -> dict:
        """Validate request-time inputs, enforcing locked values from the token."""
        ser_cls = self._get_serializer_cls(reference)
        if not ser_cls:
            return dict(params or {})
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

    # ------------------------------------------------------------------
    # Execution (replaces User scope action methods)
    # ------------------------------------------------------------------

    def execute(self, user, reference: str, params: dict) -> dict:
        """Read or write a user's NoteField value for the given scope reference."""
        slug, action = self._parse_reference(reference)
        self._validate_slug(slug, reference)

        if action == "read":
            try:
                fv = UserFieldValue.objects.get(user=user, field__slug=slug)
                return {slug: fv.value}
            except UserFieldValue.DoesNotExist:
                return {slug: None}
        else:
            note_field = NoteField.objects.get(slug=slug)
            fv, _ = UserFieldValue.objects.update_or_create(
                user=user,
                field=note_field,
                defaults={"value": params.get("content", "")},
            )
            return {slug: fv.value}

    # ------------------------------------------------------------------
    # Endpoint mapping
    # ------------------------------------------------------------------

    @classmethod
    def get_endpoint(cls, reference: str) -> dict[str, Any]:
        """Build a ``ServiceCallEndpoint`` dict for a scope reference."""
        slug, action = cls._parse_reference(reference)
        ser_cls = NoteWriteSerializer if action == "write" else None
        input_fields = (
            {name: (field.help_text or "") for name, field in ser_cls().fields.items()}
            if ser_cls
            else None
        )
        return {
            "url": f"{settings.BASE_URL}/rest/{slug}/{action}/",
            "description": f"{'Read' if action == 'read' else 'Write to'} the user's {slug.replace('_', ' ')}.",
            "input_fields": input_fields,
        }


def sync_scopes_to_broker():
    """Push the current NoteField-derived scopes to the PERMYT broker."""
    from app.core.requests.client import PermytClient  # pylint: disable=import-outside-toplevel

    slugs = NoteField.objects.values_list("slug", "name")
    scope_definitions = []
    for slug, name in slugs:
        scope_definitions.append(
            {
                "reference": f"{slug}.read",
                "name": f"Read {name}",
                "description": f"Read the user's {name} field.",
                "inputs": [],
                "default_consent_mode": "prompt_once",
                "high_sensitivity": False,
            }
        )
        scope_definitions.append(
            {
                "reference": f"{slug}.write",
                "name": f"Write {name}",
                "description": f"Write to the user's {name} field.",
                "inputs": [
                    {"name": "content", "description": "Text content to write to the field."}
                ],
                "default_consent_mode": "prompt_once",
                "high_sensitivity": False,
            }
        )

    client = PermytClient()
    return client.update_scopes(scope_definitions)
