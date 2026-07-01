"""Tests for the static Bank scope catalogue."""

from decimal import Decimal
from unittest.mock import patch

import pytest

from permyt.exceptions import InvalidInputError, InvalidScopeError

from app.core.bank.models import Movement
from app.core.requests.scopes.utils import BankScopes, sync_scopes_to_broker

EXPECTED_REFERENCES = {
    "balance.read",
    "movements.list",
    "payment.send",
    "account_ownership.check",
    "source_of_funds.read",
    "affordability.read",
}


LOCKED_PAYMENT = {
    "account": "GB29NWBK60161331926819",
    "value": "100.00",
    "currency": "EUR",
}

REQUEST_PAYMENT = {
    **LOCKED_PAYMENT,
    "name": "Acme Corp",
    "description": "Invoice 42",
}


class TestCatalogueShape:
    def test_get_available_scopes_returns_full_catalogue(self):
        refs = BankScopes().get_available_scopes()
        assert set(refs) == EXPECTED_REFERENCES
        assert len(refs) == len(EXPECTED_REFERENCES)

    def test_unknown_reference_raises(self):
        with pytest.raises(InvalidScopeError):
            BankScopes()._get_descriptor("nope.read")

    def test_invalid_action_raises(self):
        with pytest.raises(InvalidScopeError):
            BankScopes()._parse_reference("balance.write")

    def test_missing_dot_raises(self):
        with pytest.raises(InvalidScopeError):
            BankScopes()._parse_reference("balance")


@pytest.mark.django_db
class TestBalanceRead:
    def test_returns_balance_currency_iban(self, user):
        result = BankScopes().execute(user, "balance.read", {})
        assert result == {
            "amount": str(user.balance),
            "currency": user.currency,
            "iban": user.iban,
        }


@pytest.mark.django_db
class TestMovementsList:
    def test_returns_recent_movements_newest_first(self, user, make_movement):
        first = make_movement(user, reference="first")
        make_movement(user, reference="second")
        third = make_movement(user, reference="third")

        result = BankScopes().execute(user, "movements.list", {})

        refs = [m["reference"] for m in result["movements"]]
        assert refs == ["third", "second", "first"]
        assert result["movements"][0]["id"] == str(third.id)
        assert result["movements"][-1]["id"] == str(first.id)

    def test_caps_at_twenty(self, user, make_movement):
        for i in range(25):
            make_movement(user, reference=f"m{i}")
        result = BankScopes().execute(user, "movements.list", {})
        assert len(result["movements"]) == 20

    def test_other_users_movements_not_returned(self, user, make_movement, db):
        from app.core.users.factories import UserFactory

        other = UserFactory()
        make_movement(other, reference="other-only")
        make_movement(user, reference="mine")

        result = BankScopes().execute(user, "movements.list", {})
        refs = [m["reference"] for m in result["movements"]]
        assert refs == ["mine"]


@pytest.mark.django_db
class TestPaymentSend:
    def test_creates_movement_and_debits_balance(self, user):
        starting_balance = user.balance
        validated = BankScopes().validate_params(
            "payment.send", REQUEST_PAYMENT, locked=LOCKED_PAYMENT
        )
        result = BankScopes().execute(user, "payment.send", validated)

        user.refresh_from_db()
        assert user.balance == starting_balance - Decimal("100.00")

        payment = result["payment"]
        assert payment["status"] == "COMPLETED"
        assert payment["value"] == "100.00"
        assert payment["currency"] == "EUR"
        assert payment["account"] == "GB29NWBK60161331926819"
        assert payment["name"] == "Acme Corp"
        assert payment["description"] == "Invoice 42"

        movement = Movement.objects.get(id=payment["id"])
        assert movement.amount == Decimal("-100.00")
        assert movement.type == Movement.TYPE_TRANSFER
        assert movement.counterparty_iban == "GB29NWBK60161331926819"
        assert movement.counterparty_name == "Acme Corp"
        assert movement.reference == "Invoice 42"

    def test_unlocked_fields_can_be_set_at_call_time(self, user):
        # Locked side has no name / description — requester sets them freely.
        validated = BankScopes().validate_params(
            "payment.send",
            {**LOCKED_PAYMENT, "name": "Late-bound name", "description": "Late-bound desc"},
            locked=LOCKED_PAYMENT,
        )
        result = BankScopes().execute(user, "payment.send", validated)
        assert result["payment"]["name"] == "Late-bound name"
        assert result["payment"]["description"] == "Late-bound desc"

    def test_account_normalized_via_locked_canonical(self, user):
        # Locked side uses spaces; request side uses dashes — both canonicalize
        # to the same uppercased, separator-free account / IBAN.
        locked = {**LOCKED_PAYMENT, "account": "gb29 nwbk 6016 1331 9268 19"}
        request = {**REQUEST_PAYMENT, "account": "GB29-NWBK-60161331-926819"}
        validated = BankScopes().validate_params("payment.send", request, locked=locked)
        assert validated["account"] == "GB29NWBK60161331926819"


@pytest.mark.django_db
class TestLockedInputEnforcement:
    def test_matching_input_passes(self):
        validated = BankScopes().validate_params(
            "payment.send", REQUEST_PAYMENT, locked=LOCKED_PAYMENT
        )
        assert validated["value"] == Decimal("100.00")
        assert validated["account"] == "GB29NWBK60161331926819"

    def test_tampered_value_rejected(self):
        tampered = {**REQUEST_PAYMENT, "value": "1.00"}
        with pytest.raises(InvalidInputError):
            BankScopes().validate_params("payment.send", tampered, locked=LOCKED_PAYMENT)

    def test_tampered_account_rejected(self):
        tampered = {**REQUEST_PAYMENT, "account": "GB99XXXX12345678901234"}
        with pytest.raises(InvalidInputError):
            BankScopes().validate_params("payment.send", tampered, locked=LOCKED_PAYMENT)

    def test_tampered_currency_rejected(self):
        tampered = {**REQUEST_PAYMENT, "currency": "USD"}
        with pytest.raises(InvalidInputError):
            BankScopes().validate_params("payment.send", tampered, locked=LOCKED_PAYMENT)

    def test_unlocked_name_or_description_is_not_enforced(self):
        # name + description are not in locked_fields → request can differ.
        request = {**LOCKED_PAYMENT, "name": "Anything", "description": "Anything"}
        validated = BankScopes().validate_params("payment.send", request, locked=LOCKED_PAYMENT)
        assert validated["name"] == "Anything"
        assert validated["description"] == "Anything"

    def test_payment_without_locked_input_rejected(self):
        # Strict-mode: bank scopes with locked_fields require broker-locked inputs.
        with pytest.raises(InvalidInputError):
            BankScopes().validate_params("payment.send", REQUEST_PAYMENT, locked={})

    def test_inputless_scope_without_locked_passes(self):
        # balance.read and movements.list have no inputs; locked={} is fine.
        assert BankScopes().validate_params("balance.read", {}, locked={}) == {}
        assert BankScopes().validate_params("movements.list", {}, locked={}) == {}

    def test_validate_locked_canonicalizes(self):
        validated = BankScopes().validate_locked(
            "payment.send",
            {"account": "gb29 nwbk 60161331 926819", "value": "100", "currency": "eur"},
        )
        assert validated["account"] == "GB29NWBK60161331926819"
        assert validated["currency"] == "EUR"

    def test_validate_locked_strips_unlocked_fields(self):
        # validate_locked uses only_lock=True — name / description are dropped.
        validated = BankScopes().validate_locked(
            "payment.send",
            {**REQUEST_PAYMENT, "name": "should-be-dropped"},
        )
        assert "name" not in validated
        assert "description" not in validated


class TestEndpointMapping:
    def test_inputless_endpoint(self):
        endpoint = BankScopes.get_endpoint("balance.read")
        assert endpoint["url"].endswith("/rest/balance/read/")
        assert endpoint["input_fields"] is None

    def test_movements_endpoint(self):
        endpoint = BankScopes.get_endpoint("movements.list")
        assert endpoint["url"].endswith("/rest/movements/list/")
        assert endpoint["input_fields"] is None

    def test_payment_endpoint_includes_inputs(self):
        endpoint = BankScopes.get_endpoint("payment.send")
        assert endpoint["url"].endswith("/rest/payment/send/")
        assert "account" in endpoint["input_fields"]
        assert "value" in endpoint["input_fields"]
        assert "currency" in endpoint["input_fields"]
        assert "name" in endpoint["input_fields"]
        assert "description" in endpoint["input_fields"]


class TestSyncScopesToBroker:
    def test_pushes_full_catalogue_definitions(self):
        with patch(
            "app.core.requests.client.PermytClient.update_scopes",
            return_value={"ok": True},
        ) as update:
            with patch("app.core.requests.client.PermytClient.__init__", return_value=None):
                sync_scopes_to_broker()

        update.assert_called_once()
        (definitions,), _ = update.call_args
        assert len(definitions) == len(EXPECTED_REFERENCES)
        assert {d["reference"] for d in definitions} == EXPECTED_REFERENCES
        # payment.send carries input definitions; reads do not.
        by_ref = {d["reference"]: d for d in definitions}
        assert {i["name"] for i in by_ref["payment.send"]["inputs"]} == {
            "account",
            "value",
            "currency",
            "name",
            "description",
        }
        assert by_ref["balance.read"]["inputs"] == []
        assert by_ref["movements.list"]["inputs"] == []
