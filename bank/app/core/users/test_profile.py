"""Tests for the Bank account profile: User.seed_profile and ProfileView."""

import json
from decimal import Decimal

import pytest
from django.test import Client

from .factories import UserFactory
from .models import User


@pytest.mark.django_db
class TestUserModel:
    def test_iban_normalized_on_save(self):
        u = UserFactory(iban="gb29 nwbk-6016 1331 9268 19")
        u.refresh_from_db()
        assert u.iban == "GB29NWBK60161331926819"

    def test_currency_uppercased_on_save(self):
        u = UserFactory(currency="eur")
        u.refresh_from_db()
        assert u.currency == "EUR"

    def test_seed_profile_fills_bank_data_but_not_identity(self):
        # seed_profile populates the bank's own synthetic data (iban, balance,
        # currency) but NOT the account holder's identity — full_name /
        # address / birthdate are fetched from the government provider over
        # PERMYT during onboarding, so they stay blank here.
        u = User.objects.create(
            username="seedme",
            email="seedme@test.permyt.io",
            full_name="",
            iban="",
            balance=Decimal("0"),
            currency="",
        )
        u.seed_profile()
        u.refresh_from_db()
        assert u.full_name == ""
        assert u.address == ""
        assert u.birthdate == ""
        assert u.iban
        assert u.balance > Decimal("0")
        assert u.currency == "EUR"

    def test_seed_profile_idempotent(self):
        u = UserFactory(
            full_name="Pre-set Name",
            iban="GB99WAYM98765432109876",
            balance=Decimal("123.45"),
            currency="EUR",
        )
        u.seed_profile()
        u.refresh_from_db()
        assert u.full_name == "Pre-set Name"
        assert u.iban == "GB99WAYM98765432109876"
        assert u.balance == Decimal("123.45")

    def test_seed_profile_seeds_movements_once(self):
        u = UserFactory(balance=Decimal("0"))
        u.seed_profile()
        first_count = u.movements.count()
        assert first_count > 0

        u.seed_profile()  # second call should NOT seed again
        assert u.movements.count() == first_count


@pytest.mark.django_db
class TestProfileView:
    def _login(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_get_returns_profile(self, user):
        client = self._login(user)
        resp = client.get("/rest/profile/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["full_name"] == user.full_name
        assert data["iban"] == user.iban
        assert data["currency"] == user.currency
        assert data["balance"] == str(user.balance)

    def test_put_updates_full_name(self, user):
        client = self._login(user)
        resp = client.put(
            "/rest/profile/",
            data=json.dumps({"full_name": "Renamed User"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.full_name == "Renamed User"

    def test_put_ignores_non_editable_fields(self, user):
        # Only full_name is in the serializer's `fields`, so other keys are
        # silently dropped — IBAN / balance / currency must remain unchanged.
        client = self._login(user)
        original_iban = user.iban
        original_balance = user.balance
        resp = client.put(
            "/rest/profile/",
            data=json.dumps({"iban": "TAMPERED", "balance": "99999"}),
            content_type="application/json",
        )
        assert resp.status_code == 200
        user.refresh_from_db()
        assert user.iban == original_iban
        assert user.balance == original_balance

    def test_unauthenticated_rejected(self, db):
        resp = Client().get("/rest/profile/")
        assert resp.status_code in (401, 403)


@pytest.mark.django_db
class TestMovementsView:
    def _login(self, user):
        client = Client()
        client.force_login(user)
        return client

    def test_get_returns_user_movements(self, user, make_movement):
        make_movement(user, reference="alpha")
        make_movement(user, reference="beta")
        client = self._login(user)
        resp = client.get("/rest/movements/")
        assert resp.status_code == 200
        data = resp.json()
        refs = [m["reference"] for m in data["movements"]]
        assert refs == ["beta", "alpha"]

    def test_unauthenticated_rejected(self, db):
        resp = Client().get("/rest/movements/")
        assert resp.status_code in (401, 403)
