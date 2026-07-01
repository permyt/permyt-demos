from __future__ import annotations
from typing import Any

import hashlib
import json
import secrets
import requests

from joserfc import jwt, jwe
from joserfc.jwk import ECKey
from django.utils import timezone

from app.utils.crypto import load_private_key

ALGORITHMS = {
    "JWT": "ES256",
    "JWE": {"alg": "ECDH-ES+A256KW", "enc": "A256GCM"},
}


def _encrypt_jwe(payload: dict[str, Any], public_key: str) -> str:
    """
    Encrypt a payload using JWE with the recipient's public key.
    """
    recipient_key = ECKey.import_key(public_key)
    return jwe.encrypt_compact(
        ALGORITHMS["JWE"], json.dumps(payload).encode("utf-8"), recipient_key
    )


def _create_proof(payload: dict[str, Any], private_key) -> str:
    """
    Create a proof of possession by signing a hash of the payload.
    """
    payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    proof_claims = {
        "payload_hash": payload_hash,
        "timestamp": timezone.now().isoformat(),
    }
    key = ECKey.import_key(private_key) if not isinstance(private_key, ECKey) else private_key
    return jwt.encode({"alg": ALGORITHMS["JWT"]}, proof_claims, key)


def send_encrypted_request(  # pylint: disable=too-many-arguments
    url: str,
    action: str,
    data: dict[str, Any],
    *,
    recipient_public_key: str,
    private_key: str,
    tries: int = 3,
) -> Any:
    """
    Send a signed and encrypted POST request to a service.

    This is the canonical outbound transport for every PERMYT-to-service call.
    Every body carries an outer ``action`` discriminator so the receiving
    service can dispatch on a single webhook URL.

    Args:
        url: Target callback URL.
        action: Required protocol-level action discriminator
            (e.g. ``"token_request"``, ``"request_status"``, ``"user_connect"``).
        data: Inner data dict — JWE-encrypted with ``recipient_public_key``.
        recipient_public_key: PEM public key of the recipient service.
        private_key: PEM private key used to sign the proof. For PERMYT calls,
            this is the per-service ``permyt_private_key`` from ``ServiceCredentials``.
        tries: Retry attempts on transient failures.

    Returns:
        Parsed JSON response, or ``{"content": ..., "status_code": ...}`` if
        the response is not valid JSON after exhausting retries.
    """
    payload = {
        "data": _encrypt_jwe(data, recipient_public_key),
        "timestamp": timezone.now().isoformat(),
        "nonce": secrets.token_hex(32),
    }

    body = {
        "action": action,
        "payload": payload,
        "proof": _create_proof(payload, private_key=private_key),
    }

    try:
        response = requests.post(url, json=body, timeout=30)
    except requests.RequestException as exc:
        if tries > 0:
            return send_encrypted_request(
                url,
                action,
                data,
                recipient_public_key=recipient_public_key,
                private_key=private_key,
                tries=tries - 1,
            )
        raise exc

    try:
        return response.json()
    except Exception:  # pylint: disable=broad-except
        if tries > 0:
            return send_encrypted_request(
                url,
                action,
                data,
                recipient_public_key=recipient_public_key,
                private_key=private_key,
                tries=tries - 1,
            )
        return {"content": response.content, "status_code": response.status_code}


class EncryptedRequestMixin:
    """
    Mixin to add encrypted request capabilities to a model.

    Subclasses must expose ``self.private_key`` (PEM string or loaded key).
    The instance-bound ``request()`` method is a thin wrapper around the
    free-standing :func:`send_encrypted_request` so callers without a model
    instance (e.g. serializers handling user-initiated flows) can reuse the
    same transport without instantiating a class.
    """

    ALGORITHMS = ALGORITHMS

    def request(  # pylint: disable=too-many-arguments
        self,
        url: str,
        action: str,
        data: dict[str, Any],
        recipient_public_key: str,
        *,
        private_key: str = None,
        tries: int = 3,
    ) -> Any:
        """
        Makes a signed and encrypted POST request from this model instance.

        Args:
            url: API endpoint URL.
            action: Protocol-level action discriminator (required).
            data: Data to send in the request.
            recipient_public_key: Target service public key for encryption.
            private_key: Override signing key. Defaults to ``self.private_key``.
        """
        return send_encrypted_request(
            url=url,
            action=action,
            data=data,
            recipient_public_key=recipient_public_key,
            private_key=private_key or self.private_key,
            tries=tries,
        )

    # -------------------------------------------------------------------------
    # Internal methods for key handling, signing & encryption
    # -------------------------------------------------------------------------

    def _load_private_key(self, private_key: str):
        """
        Load private key from a PEM string or file path.

        Args:
            private_key (str): PEM string or path to PEM file.

        Returns:
            Private key object for signing operations.

        Raises:
            ValueError: If the key format is invalid or file does not exist.
        """
        return load_private_key(private_key)

    def _create_proof(self, payload: dict[str, Any], private_key=None) -> str:
        """
        Create a proof of possession by signing a hash of the payload.

        This proves the sender actually created this specific request,
        not just that they hold a valid key.
        """
        return _create_proof(payload, private_key=private_key or self.private_key)

    def _sign_jwt(self, payload: dict[str, Any], private_key=None) -> str:
        """
        Sign a payload as a JWT using the client's private key (ES256).
        """
        key = private_key or self.private_key
        key = ECKey.import_key(key) if not isinstance(key, ECKey) else key
        return jwt.encode({"alg": ALGORITHMS["JWT"]}, payload, key)

    def _encrypt_jwe(self, payload: dict[str, Any], public_key: str) -> str:
        """
        Encrypt a payload using JWE with the recipient's public key.
        """
        return _encrypt_jwe(payload, public_key)
