from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from joserfc import jwt
from joserfc.jwt import JWTClaimsRegistry
from permyt import PermytClient as BasePermytClient, exceptions
from permyt.typing import (
    ScopeGrant,
    ServiceCallEndpoint,
    TokenMetadata,
    TokenRequestData,
)

from django.conf import settings
from django.db import IntegrityError, transaction

from app.core.logs.models import Log
from app.core.users.models import User, LoginToken

from .models import RequestToken, Nonce
from .scopes.utils import GovernmentScopes


class PermytClient(BasePermytClient):
    """Provider-side PERMYT client for the Government provider.

    Subclasses the SDK's ``PermytClient`` to implement identity, replay
    protection, token management, scope execution, and user connect.

    See README — "Key integration points" for an overview of how this
    class maps to the SDK.
    """

    def __init__(self):
        super().__init__(host=settings.PERMYT_HOST)

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------

    def get_service_id(self) -> str:
        """Return the registered service ID from Django settings."""
        return settings.PERMYT_SERVICE_ID

    def get_private_key(self) -> str:
        """Return the path to the connector private key (ES256)."""
        return settings.PRIVATE_KEY_PATH

    def get_permyt_public_key(self) -> str:
        """Load the PERMYT broker's public key for signature verification."""
        return Path(settings.PERMYT_PUBLIC_KEY_PATH).read_text(encoding="utf-8")

    # ------------------------------------------------------------------
    # Replay protection
    # ------------------------------------------------------------------

    def _validate_nonce_and_timestamp(self, nonce: str, timestamp: str) -> None:
        """Reject replayed or expired inbound requests.

        Checks the timestamp is within ``NONCE_TTL_SECONDS`` of now and
        atomically stores the nonce to prevent reuse.
        """
        ts = datetime.fromisoformat(timestamp)
        now = datetime.now(timezone.utc)
        window = timedelta(seconds=settings.NONCE_TTL_SECONDS)

        if abs(now - ts) > window:
            raise exceptions.ExpiredRequestError("Request timestamp is outside the valid window.")

        try:
            with transaction.atomic():
                Nonce.objects.create(value=nonce)
        except IntegrityError as exc:
            raise exceptions.ExpiredRequestError("Nonce has already been used.") from exc

    # ------------------------------------------------------------------
    # User resolution
    # ------------------------------------------------------------------

    def resolve_user(self, permyt_user_id: str | None = None) -> User:
        """Look up the local User by ``permyt_user_id``.

        Called by the SDK during ``handle_token_request`` to map the
        broker's user identifier to a local account.
        """
        if not permyt_user_id:
            raise exceptions.InvalidUserError("permyt_user_id is required.")
        try:
            return User.objects.get(permyt_user_id=permyt_user_id)
        except User.DoesNotExist as exc:
            raise exceptions.InvalidUserError(
                f"User with permyt_user_id {permyt_user_id} does not exist."
            ) from exc

    # ------------------------------------------------------------------
    # Token storage
    # ------------------------------------------------------------------

    def store_token(
        self, token: str, user: Any, data: TokenRequestData, expires_at: datetime
    ) -> None:
        """Persist a broker-issued request token.

        Validates locked scope inputs via ``GovernmentScopes.validate_locked``,
        extracts the JTI from the signed JWT, and creates a ``RequestToken``
        record. Logs the event via ``Log.upsert_request``.
        """
        scope: ScopeGrant = data.get("scope") or {}
        scopes = GovernmentScopes()
        canonical = {ref: scopes.validate_locked(ref, locked) for ref, locked in scope.items()}

        # Extract JTI from signed JWT — matches what get_token_metadata looks up by
        claims = jwt.decode(token, self.private_key).claims
        jti = claims["jti"]

        request_id = data.get("request_id")

        RequestToken.objects.create(
            jti=jti,
            user=user,
            request_id=request_id,
            service_id=data.get("service_id"),
            service_public_key=data.get("service_public_key"),
            scope=canonical,
            expires_at=expires_at,
        )
        Log.upsert_request(
            user,
            str(request_id),
            action="token_issued",
            data={
                "service_id": str(data.get("service_id")) if data.get("service_id") else None,
                "scopes": list(scope.keys()),
            },
        )

    # ------------------------------------------------------------------
    # Token retrieval (single-use, atomic)
    # ------------------------------------------------------------------

    def get_token_metadata(self, token: str) -> TokenMetadata:
        """Retrieve and consume a single-use request token.

        Decodes the JWT, atomically locks the token row via
        ``select_for_update`` so two concurrent redemptions cannot both
        observe ``used=False``, validates expiry, marks the token used,
        and returns the metadata dict. Includes ``request_id`` as an
        extra key for downstream logging in ``process_request``.
        """
        claims = jwt.decode(token, self.private_key).claims
        JWTClaimsRegistry().validate(claims)
        jti = claims["jti"]

        with transaction.atomic():
            try:
                record = RequestToken.objects.select_for_update().get(jti=jti)
            except RequestToken.DoesNotExist as exc:
                raise exceptions.InvalidTokenError("Token not found.") from exc

            if record.used:
                raise exceptions.TokenAlreadyUsedError("Token has already been used.")

            if record.expires_at < datetime.now(timezone.utc):
                raise exceptions.TokenExpiredError("Token has expired.")

            record.used = True
            record.save(update_fields=["used"])

        return {
            "user": record.user,
            "scope": record.scope,
            "service_public_key": record.service_public_key,
            "expires_at": record.expires_at.isoformat(),
            "request_id": str(record.request_id),
        }

    # ------------------------------------------------------------------
    # Scope -> endpoint mapping
    # ------------------------------------------------------------------

    def get_endpoints_for_scope(self, scope: ScopeGrant) -> list[ServiceCallEndpoint]:
        """Map granted scope references to provider endpoint URLs."""
        return [GovernmentScopes.get_endpoint(ref) for ref in scope]

    # ------------------------------------------------------------------
    # Service call processing
    # ------------------------------------------------------------------

    def process_request(
        self, metadata: TokenMetadata, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Execute the granted scopes against the user's data.

        Iterates each scope in the grant, validates inputs (enforcing
        locked values from the token), and delegates to
        ``GovernmentScopes.execute``. Updates the Log row to
        ``data_served``.
        """
        user = metadata["user"]
        granted: ScopeGrant = metadata["scope"]
        data = data or {}

        scopes = GovernmentScopes()
        results: dict[str, Any] = {}

        # SDK calls each endpoint separately — data is params, not {scope: params}.
        # Iterate granted scopes; use data as params (requester may supply inputs).
        for reference, locked in granted.items():
            params = data.get(reference, data)
            validated = scopes.validate_params(reference, params or {}, locked=locked)
            results[reference] = scopes.execute(user, reference, validated)

        request_id = metadata.get("request_id")
        if request_id:
            Log.upsert_request(
                user,
                request_id,
                action="data_served",
                data={"scopes": list(granted.keys())},
            )
        else:
            Log.info("data_served", data={"scopes": list(granted.keys())}, user=user)

        return results

    # ------------------------------------------------------------------
    # Requester-side stub (required by SDK abstract class)
    # ------------------------------------------------------------------

    def _prepare_data_for_endpoint(
        self, request_id: str, endpoint: ServiceCallEndpoint
    ) -> dict[str, Any]:
        """Stub required by SDK. Providers do not call other services."""
        return {}

    # ------------------------------------------------------------------
    # User connect (QR-login)
    # ------------------------------------------------------------------

    def process_user_connect(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Handle the ``user_connect`` callback from the PERMYT broker.

        Called when a user scans the QR code on the login page. Validates
        the login token, creates or links the local User via
        ``permyt_user_id``, seeds note fields, and marks the session as
        authenticated.
        """
        permyt_user_id = data.get("permyt_user_id")
        with Log.activity(
            "user_connect",
            data={"permyt_user_id": str(permyt_user_id) if permyt_user_id else None},
        ) as ctx:
            if not permyt_user_id:
                raise exceptions.InvalidInputError("permyt_user_id is required for user connect.")

            try:
                token = LoginToken.objects.get(token=data.get("token"))
            except LoginToken.DoesNotExist as exc:
                raise exceptions.InvalidInputError("Invalid login token.") from exc

            if token.user:
                record = token.user
                if record.permyt_user_id is None:
                    # Registration QR: link the scanned PERMYT profile to the
                    # pre-created person/business record operators registered.
                    record.permyt_user_id = permyt_user_id
                    record.save(update_fields=["permyt_user_id"])
                elif record.permyt_user_id != permyt_user_id:
                    raise exceptions.InvalidUserError(
                        "Record already linked to a different permyt profile."
                    )
                ctx.user = record
            else:
                # Browser-login QR: honour the Personal/Business choice the
                # visitor made on the landing page (stored on the token).
                existing = User.objects.filter(permyt_user_id=permyt_user_id).first()
                if existing:
                    if existing.profile_type != token.profile_type:
                        # The scanned identity is already registered under a
                        # different account type than the visitor selected.
                        # Reject and surface a friendly error to the page.
                        current = existing.get_profile_type_display()
                        token.error = (
                            f"This identity is registered as a {current} account. "
                            f"Choose “{current}” to sign in."
                        )
                        token.save(update_fields=["error"])
                        return {"logged": False, "error": token.error}
                    ctx.user = existing
                else:
                    ctx.user = User.objects.create(
                        username=permyt_user_id,
                        permyt_user_id=permyt_user_id,
                        profile_type=token.profile_type,
                    )

            # Seed any blank fields with synthetic data (type-aware).
            ctx.user.seed()

            if token.session_id:
                # Browser-login QR — log the polling browser session in.
                token.login(ctx.user)
            else:
                # Registration QR — no browser session to authenticate.
                token.logged_in = True
                token.save(update_fields=["logged_in"])
            return {"logged": True}

    # ------------------------------------------------------------------
    # User disconnect
    # ------------------------------------------------------------------

    def process_user_disconnect(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Handle the ``user_disconnect`` callback from the PERMYT broker.

        Idempotent — a repeat call for an already-disconnected user is a
        no-op. Regular users have no non-PERMYT login path, so the row is
        deleted outright (cascade clears LoginTokens and the citizen
        profile). Privileged users (staff, superuser, account manager)
        keep their account: only ``permyt_user_id`` is nulled and login
        tokens are dropped so they can still sign in via the admin paths.
        """
        permyt_user_id = data.get("permyt_user_id")
        with Log.activity(
            "user_disconnect",
            data={"permyt_user_id": str(permyt_user_id) if permyt_user_id else None},
        ):
            if not permyt_user_id:
                raise exceptions.InvalidInputError(
                    "permyt_user_id is required for user disconnect."
                )

            try:
                user = User.objects.get(permyt_user_id=permyt_user_id)
            except User.DoesNotExist:
                return {"disconnected": True}

            if user.is_staff or user.is_superuser or user.is_account_manager:
                LoginToken.objects.filter(user=user).delete()
                user.permyt_user_id = None
                user.save()
            else:
                user.delete()
            return {"disconnected": True}

    # ------------------------------------------------------------------
    # Token revoke (sibling fan-out)
    # ------------------------------------------------------------------

    def process_token_revoke(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Handle the ``token_revoke`` callback from the PERMYT broker.

        Fired when the user disconnects or blacklists a *peer* service in the
        same profile. The broker fans this out to every other connection so
        each can drop in-flight tokens involving the blocked peer before they
        age out of their natural TTL. We invalidate every still-valid token
        this provider issued for the user that was issued to the blocked peer
        — matched by broker ``service_id`` OR the peer's
        ``service_public_key``. Idempotent.

        ``service_public_key`` is stored encrypted (not queryable), so the
        match runs in Python over the user's unused tokens.
        """
        permyt_user_id = data.get("permyt_user_id")
        blocked_service_id = data.get("blocked_service_id")
        blocked_service_public_key = data.get("blocked_service_public_key")
        with Log.activity(
            "token_revoke",
            data={
                "permyt_user_id": str(permyt_user_id) if permyt_user_id else None,
                "blocked_service_id": str(blocked_service_id) if blocked_service_id else None,
                "reason": data.get("reason"),
            },
        ) as ctx:
            if not permyt_user_id:
                raise exceptions.InvalidInputError("permyt_user_id is required for token revoke.")

            try:
                user = User.objects.get(permyt_user_id=permyt_user_id)
            except User.DoesNotExist:
                return {"revoked": 0}
            ctx.user = user

            revoke_ids = [
                token.id
                for token in RequestToken.objects.filter(user=user, used=False)
                if (blocked_service_id and str(token.service_id) == str(blocked_service_id))
                or (
                    blocked_service_public_key
                    and token.service_public_key == blocked_service_public_key
                )
            ]
            revoked = (
                RequestToken.objects.filter(id__in=revoke_ids).update(used=True)
                if revoke_ids
                else 0
            )
            return {"revoked": revoked}

    # ------------------------------------------------------------------
    # Status callbacks (no-op)
    # ------------------------------------------------------------------

    def process_request_status(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """No-op for providers — status callbacks are requester-only."""
        return {"received": True}
