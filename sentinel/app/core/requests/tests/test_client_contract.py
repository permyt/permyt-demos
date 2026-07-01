"""
Tests for the requester PermytClient contract.

Exercises the client's abstract-method implementations:
* Nonce replay protection (atomic insert)
* Token single-use enforcement (select_for_update regression + threaded race)
* _prepare_data_for_endpoint (returns empty dict)
"""

import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from django.db import connection

from permyt.exceptions import (
    ExpiredRequestError,
    InvalidTokenError,
    TokenAlreadyUsedError,
    TokenExpiredError,
)


class _FakeClaims(dict):
    """Stand-in for joserfc decode result used by get_token_metadata."""

    @property
    def claims(self):
        return self


@pytest.mark.django_db
class TestNonceAndTimestamp:
    def test_fresh_nonce_accepted(self, mock_permyt_client):
        mock_permyt_client._validate_nonce_and_timestamp(
            "nonce-1", datetime.now(timezone.utc).isoformat()
        )

    def test_nonce_reuse_rejected(self, mock_permyt_client):
        ts = datetime.now(timezone.utc).isoformat()
        mock_permyt_client._validate_nonce_and_timestamp("nonce-2", ts)
        with pytest.raises(ExpiredRequestError, match="Nonce"):
            mock_permyt_client._validate_nonce_and_timestamp("nonce-2", ts)

    def test_expired_timestamp_rejected(self, mock_permyt_client):
        old = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        with pytest.raises(ExpiredRequestError, match="timestamp"):
            mock_permyt_client._validate_nonce_and_timestamp("nonce-old", old)

    def test_future_timestamp_rejected(self, mock_permyt_client):
        future = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat()
        with pytest.raises(ExpiredRequestError, match="timestamp"):
            mock_permyt_client._validate_nonce_and_timestamp("nonce-future", future)


@pytest.mark.django_db
class TestTokenMetadata:
    def test_returns_persisted_scope_grant(self, mock_permyt_client, user, make_token):
        scope_grant = {"sanctions.check": {}}
        record = make_token(user, scope_grant=scope_grant)
        with patch(
            "app.core.requests.client.jwt.decode",
            return_value=_FakeClaims({"jti": record.jti}),
        ):
            metadata = mock_permyt_client.get_token_metadata("opaque-token")
        assert metadata["scope"] == scope_grant
        assert metadata["user"].pk == user.pk

    def test_single_use_enforcement(self, mock_permyt_client, user, make_token):
        record = make_token(user)
        with patch(
            "app.core.requests.client.jwt.decode",
            return_value=_FakeClaims({"jti": record.jti}),
        ):
            mock_permyt_client.get_token_metadata("opaque-token")
            with pytest.raises(TokenAlreadyUsedError):
                mock_permyt_client.get_token_metadata("opaque-token")

    def test_select_for_update_is_used(self, mock_permyt_client, user, make_token):
        # Regression: get_token_metadata MUST acquire a row-level lock so two
        # concurrent redemptions cannot both observe used=False.
        from app.core.requests.models import RequestToken

        record = make_token(user)
        original = RequestToken.objects.select_for_update
        calls: list = []

        def spy(*args, **kwargs):
            calls.append((args, kwargs))
            return original(*args, **kwargs)

        with (
            patch.object(RequestToken.objects, "select_for_update", side_effect=spy),
            patch(
                "app.core.requests.client.jwt.decode",
                return_value=_FakeClaims({"jti": record.jti}),
            ),
        ):
            mock_permyt_client.get_token_metadata("opaque-token")

        assert calls, "get_token_metadata must call select_for_update"

    @pytest.mark.django_db(transaction=True)
    def test_concurrent_redemption_yields_one_success(self, mock_permyt_client, user, make_token):
        # End-to-end race: two threads redeem the same JTI; exactly one wins.
        # The losing redemption either observes used=True (TokenAlreadyUsedError)
        # or hits a write-lock on SQLite (OperationalError) — both prove that
        # the atomic+select_for_update block prevents double-redemption.
        from django.db import OperationalError

        record = make_token(user)
        successes: list = []
        failures: list = []
        barrier = threading.Barrier(2)

        def redeem():
            try:
                with patch(
                    "app.core.requests.client.jwt.decode",
                    return_value=_FakeClaims({"jti": record.jti}),
                ):
                    barrier.wait(timeout=5)
                    successes.append(mock_permyt_client.get_token_metadata("opaque-token"))
            except (TokenAlreadyUsedError, OperationalError) as exc:
                failures.append(exc)
            finally:
                connection.close()

        t1 = threading.Thread(target=redeem)
        t2 = threading.Thread(target=redeem)
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert len(successes) == 1, f"expected exactly one success, got {len(successes)}"
        assert len(failures) == 1, f"expected exactly one losing redemption, got {len(failures)}"

    def test_unknown_jti_rejected(self, mock_permyt_client):
        with (
            patch(
                "app.core.requests.client.jwt.decode",
                return_value=_FakeClaims({"jti": "no-such-jti"}),
            ),
            pytest.raises(InvalidTokenError),
        ):
            mock_permyt_client.get_token_metadata("opaque-token")

    def test_expired_token_rejected(self, mock_permyt_client, user, make_token):
        record = make_token(user, expires_in_minutes=-1)
        with (
            patch(
                "app.core.requests.client.jwt.decode",
                return_value=_FakeClaims({"jti": record.jti}),
            ),
            pytest.raises(TokenExpiredError),
        ):
            mock_permyt_client.get_token_metadata("opaque-token")


class TestPrepareDataForEndpoint:
    def test_returns_empty_dict(self, mock_permyt_client):
        result = mock_permyt_client._prepare_data_for_endpoint(
            "req-123", {"url": "http://provider/api/something", "scope": "test"}
        )
        assert result == {}
