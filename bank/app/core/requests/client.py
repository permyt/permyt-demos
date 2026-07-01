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
from app.utils.websocket import send_to_websocket

from .models import RequestToken, Nonce
from .scopes.utils import BankScopes

# Plain-language brief the broker's AI uses to resolve the minimal scopes
# (name.read + address.read + birthdate.read on the government provider).
ONBOARDING_DESCRIPTION = (
    "Bank onboarding: read the new account holder's full legal name, "
    "residential address, and date of birth to open their account."
)

# A business account holder is a company — ask the government provider for the
# COMPANY's registered identity, not a person's. (The broker's scope picker is
# not yet smart enough to infer this from a generic "name" request, so we make
# the company intent explicit.)
ONBOARDING_DESCRIPTION_BUSINESS = (
    "Business bank onboarding: read the company's registered legal name, "
    "company registration number and registered business address to open its "
    "account."
)


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

        Validates locked scope inputs via ``BankScopes.validate_locked``,
        extracts the JTI from the signed JWT, and creates a ``RequestToken``
        record. Logs the event via ``Log.upsert_request``.
        """
        scope: ScopeGrant = data.get("scope") or {}
        scopes = BankScopes()
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
        return [BankScopes.get_endpoint(ref) for ref in scope]

    # ------------------------------------------------------------------
    # Service call processing
    # ------------------------------------------------------------------

    def process_request(
        self, metadata: TokenMetadata, data: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Execute the granted scopes against the user's data.

        Iterates each scope in the grant, validates inputs (enforcing
        locked values from the token), and delegates to
        ``BankScopes.execute``. Updates the Log row to
        ``data_served``.
        """
        user = metadata["user"]
        granted: ScopeGrant = metadata["scope"]
        data = data or {}

        scopes = BankScopes()
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
        """Build per-endpoint inputs when calling a provider as a requester.

        The bank's only outbound request is the onboarding identity fetch,
        whose scopes (``name.read`` / ``address.read`` / ``birthdate.read``)
        declare no inputs — so there is nothing to send and ``{}`` is correct.
        """
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
                if token.user.permyt_user_id != permyt_user_id:
                    raise exceptions.InvalidUserError(
                        "User already linked to a different permyt profile."
                    )
                ctx.user = token.user
            else:
                ctx.user, created = User.objects.get_or_create(
                    permyt_user_id=permyt_user_id,
                    defaults={
                        "username": permyt_user_id,
                        "profile_type": token.profile_type,
                    },
                )
                # Honour the Personal/Business choice for a fresh account so
                # onboarding requests the right (person vs company) identity.
                if created and ctx.user.profile_type != token.profile_type:
                    ctx.user.profile_type = token.profile_type
                    ctx.user.save(update_fields=["profile_type"])

            # Seed the bank's own synthetic data (iban, balance, movements).
            # The account holder's identity is fetched from PERMYT below.
            ctx.user.seed_profile()

            token.login(ctx.user)

            # Kick off the requester-side identity fetch only for brand-new
            # accounts with no identity yet. Accounts that already have a name
            # — returning users, or accounts created before this onboarding
            # update — are already populated, so mark them onboarded instead
            # of firing a fresh request that would leave the banner spinning.
            if not ctx.user.onboarding_complete:
                if ctx.user.full_name:
                    ctx.user.onboarding_complete = True
                    ctx.user.save(update_fields=["onboarding_complete", "updated_at"])
                else:
                    self._fire_identity_request(ctx.user)

            return {"logged": True}

    def _fire_identity_request(self, user: User) -> None:
        """Submit the onboarding identity access request and persist its id.

        The bank acts as a PERMYT *requester* here: it asks the broker for the
        account holder's verified name, address, and date of birth. The broker
        runs AI scope evaluation, routes user approval, and posts status
        updates back to our registered service callback (handled by
        ``process_request_status``); ``sync_onboarding`` also pulls status from
        the broker as a backstop.
        """
        description = (
            ONBOARDING_DESCRIPTION_BUSINESS if user.is_business else ONBOARDING_DESCRIPTION
        )
        try:
            response = self.request_access(
                {
                    "user_id": str(user.permyt_user_id),
                    "description": description,
                    # No per-request callback_url on purpose: the broker then
                    # falls back to our REGISTERED service callback — the same
                    # endpoint ``user_connect`` is delivered to — which is
                    # reliable regardless of this app's BASE_URL config. (A
                    # BASE_URL-derived callback can point somewhere the broker
                    # can't reach, silently dropping the completion callback.)
                    # ``sync_onboarding`` also pulls status as a backstop.
                }
            )
        except Exception as exc:  # pylint: disable=broad-exception-caught
            # Any failure to submit (PermytError or transport/other) must surface
            # as a failed onboarding rather than leave the banner spinning forever.
            Log.error(
                "identity_request",
                data={"description": description, "error": str(exc)},
                user=user,
            )
            self._ws_onboarding(user, "onboarding_failed", reason=str(exc))
            return

        request_id = response.get("request_id") if isinstance(response, dict) else None
        status = response.get("status") if isinstance(response, dict) else None

        if request_id:
            user.onboarding_request_id = str(request_id)
            user.save(update_fields=["onboarding_request_id", "updated_at"])
            Log.upsert_request(
                user,
                str(request_id),
                action="identity_submitted",
                data={"kind": "identity", "status": status},
            )
        self._ws_onboarding(user, "onboarding_started", status=status)

    @staticmethod
    def _ws_onboarding(user: User, event: str, **payload) -> None:
        """Push an onboarding lifecycle event to the user's dashboard socket.

        The dashboard JS listens on ``/ws/`` (group ``user-{id}``) and reveals
        the verified identity once ``onboarding_verified`` arrives.
        """
        if not user or not user.id:
            return
        send_to_websocket(
            f"user-{user.id}",
            {"type": "onboarding", "event": event, **payload},
        )

    # ------------------------------------------------------------------
    # User disconnect
    # ------------------------------------------------------------------

    def process_user_disconnect(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Handle the ``user_disconnect`` callback from the PERMYT broker.

        Idempotent — a repeat call for an already-disconnected user is a
        no-op. Regular users have no non-PERMYT login path, so the row is
        deleted outright (cascade clears LoginTokens and account state).
        Privileged users (staff, superuser, account manager) keep their
        account: only ``permyt_user_id`` is nulled and login tokens are
        dropped so they can still sign in via the admin paths.
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
    # Requester status callbacks (onboarding identity fetch)
    # ------------------------------------------------------------------

    TERMINAL_FAILURES = {"rejected", "incomplete", "unavailable"}

    def process_request_status(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Handle broker status callbacks for the onboarding identity request.

        The bank is a requester here. When the user approves on their mobile
        app the broker drives the request to ``completed`` and includes the
        encrypted token bundle in ``services`` — we call the government
        provider, extract the verified identity, write it onto the account,
        and push a websocket event so the dashboard reveals it live. Terminal
        failures surface a friendly reason. Unknown request ids are ignored
        (a provider-side status callback would never match an onboarding id).
        """
        data = data or {}
        request_id = data.get("request_id")
        if not request_id:
            return {"received": True}
        request_id = str(request_id)

        user = User.objects.filter(onboarding_request_id=request_id).first()
        if not user:
            return {"received": True}

        status = data.get("status")
        Log.upsert_request(
            user,
            request_id,
            action=status or "updated",
            data={"kind": "identity", "status": status},
        )
        self._ws_onboarding(user, "onboarding_status", status=status)

        if status == "completed":
            self._handle_identity_completion(user, request_id, data.get("services") or [])
        elif status in self.TERMINAL_FAILURES:
            reason = data.get("reason") or status
            Log.upsert_request(
                user,
                request_id,
                action="ended",
                data={"kind": "identity", "status": status, "reason": reason},
                success=False,
            )
            self._ws_onboarding(user, "onboarding_failed", reason=str(reason))

        return {"received": True}

    def sync_onboarding(self, user) -> bool:
        """Actively pull the onboarding request status from the broker and
        finalize if it has completed.

        The push callback (``process_request_status``) is best-effort — if the
        broker can't reach our callback URL, or the event is otherwise lost,
        the account would hang on "fetching" forever. The dashboard's poll calls
        this so every tick reconciles against the broker via ``check_access``,
        making completion pull-driven and robust. Returns the (possibly updated)
        ``onboarding_complete`` flag.
        """
        if user.onboarding_complete:
            return True
        if not user.onboarding_request_id:
            return False
        try:
            result = self.check_access(str(user.onboarding_request_id))
        except Exception:  # pylint: disable=broad-exception-caught
            return False
        status = result.get("status") if isinstance(result, dict) else None
        if status == "completed":
            self._handle_identity_completion(
                user, str(user.onboarding_request_id), result.get("services") or []
            )
        elif status in self.TERMINAL_FAILURES:
            self._ws_onboarding(
                user, "onboarding_failed", reason=result.get("reason") or status
            )
        user.refresh_from_db()
        return user.onboarding_complete

    def _handle_identity_completion(self, user: User, request_id: str, services: list[Any]) -> None:
        """Call the identity provider, map the response, and verify the user.

        The government provider returns ``full_name`` / ``address`` /
        ``birthdate`` keys. We write whatever we received, mark the account
        verified, and push ``onboarding_verified`` with the resolved fields.
        """
        if user.onboarding_complete:
            # Already finalized (e.g. the pull path beat a duplicate push
            # callback). Don't redeem the single-use token again — just
            # re-announce verified so any late UI catches up.
            self._ws_onboarding(
                user,
                "onboarding_verified",
                full_name=user.full_name,
                address=user.address,
                birthdate=user.birthdate,
            )
            return

        if not services:
            Log.upsert_request(
                user,
                request_id,
                action="identity_empty",
                data={"kind": "identity", "status": "completed", "note": "no services"},
                success=False,
            )
            self._ws_onboarding(user, "onboarding_failed", reason="No identity provider responded.")
            return

        try:
            responses = self.call_services(services)
        except Exception as exc:  # pylint: disable=broad-exception-caught
            Log.upsert_request(
                user,
                request_id,
                action="identity_call_error",
                data={"kind": "identity", "error": str(exc)},
                success=False,
            )
            self._ws_onboarding(user, "onboarding_failed", reason=str(exc))
            return

        identity = self._extract_identity(responses)

        if not identity.get("full_name"):
            # No verified holder name came back (e.g. a business account whose
            # PERMYT profile isn't a registered company). Fail clearly with a
            # retry rather than open a blank, nameless account.
            who = "company" if user.is_business else "identity"
            Log.upsert_request(
                user,
                request_id,
                action="identity_empty",
                data={"kind": "identity", "status": "completed", "note": f"no {who} name"},
                success=False,
            )
            self._ws_onboarding(
                user,
                "onboarding_failed",
                reason=(
                    "No company record was found for your profile — make sure it's a "
                    "registered business, then request again."
                    if user.is_business
                    else "We couldn't read your verified identity. Please request again."
                ),
            )
            return

        user.full_name = identity.get("full_name") or user.full_name
        user.address = identity.get("address") or user.address
        user.birthdate = identity.get("birthdate") or user.birthdate
        user.onboarding_complete = True
        user.save(
            update_fields=[
                "full_name",
                "address",
                "birthdate",
                "onboarding_complete",
                "updated_at",
            ]
        )

        Log.upsert_request(
            user,
            request_id,
            action="identity_verified",
            data={
                "kind": "identity",
                "status": "completed",
                "fields": [k for k, v in identity.items() if v],
            },
        )
        self._ws_onboarding(
            user,
            "onboarding_verified",
            full_name=user.full_name,
            address=user.address,
            birthdate=user.birthdate,
        )

    @staticmethod
    def _extract_identity(responses: list[Any]) -> dict[str, str]:
        """Merge provider responses into ``{full_name, address, birthdate}``.

        Tolerant of key aliases so the demo survives small provider changes.
        Picks the first non-empty value seen for each field.
        """
        aliases = {
            # ``legal_name`` covers the company.registry.read shape for a
            # business account (the holder name is the company's legal name).
            "full_name": ("full_name", "name", "legal_name", "display_name"),
            "address": ("address", "registered_address", "postal_address"),
            "birthdate": ("birthdate", "date_of_birth", "dob"),
        }
        # Provider responses are keyed by scope reference, e.g.
        # ``{"name.read": {"name": "..."}, "address.read": {"address": "..."}}``.
        # Flatten one level so we can match leaf fields regardless of whether a
        # provider nests them under the reference or returns them at the top.
        flat: dict[str, Any] = {}
        for resp in responses:
            if not isinstance(resp, dict):
                continue
            for key, value in resp.items():
                if isinstance(value, dict):
                    for inner_key, inner_value in value.items():
                        flat.setdefault(inner_key, inner_value)
                else:
                    flat.setdefault(key, value)

        out: dict[str, str] = {}
        for field, keys in aliases.items():
            for key in keys:
                if flat.get(key):
                    out[field] = str(flat[key])
                    break
        return out
