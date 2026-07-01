"""Tests for the PERMYT-facts → Stripe field mapper and the Stripe service stub."""

from app.core.stripe_kyc import mapper, service

PROVIDER_RESPONSES = [
    {
        "company.registry.read": {
            "legal_name": "London Coffee Roasters Ltd",
            "registration_number": "07654321",
            "incorporation_date": "2015-06-15",
            "country": "GB",
            "structure": "private_corporation",
        },
        "company.tax_id.read": {"tax_id": "GB123456789"},
        "company.address.read": {"registered_address": "42 Brick Lane, London E1 6QL"},
        "company.profile.read": {"mcc": "5499", "website": "https://lcr.example.com"},
        "company.ownership.read": {
            "owners": [
                {
                    "first_name": "Eleanor",
                    "last_name": "Pembroke",
                    "birthdate": "1972-03-12",
                    "address": "10 Clerkenwell Road, London EC1M 5QA",
                    "country": "GB",
                    "id_number": "PEMB720312",
                    "ownership_percent": 80,
                    "is_representative": True,
                },
                {
                    "first_name": "James",
                    "last_name": "Hartley",
                    "birthdate": "1978-07-05",
                    "address": "22 Shoreditch High St, London E1 6PG",
                    "country": "GB",
                    "id_number": "HART780705",
                    "ownership_percent": 20,
                    "is_representative": False,
                },
            ]
        },
    },
    {"products.read": {"products": ["Single-origin beans", "Subscriptions"]}},
]


class TestMapper:
    """build_payload maps verified facts to Stripe Account/Person params."""

    def test_merge_responses_flattens_by_reference(self):
        combined = mapper.merge_responses(PROVIDER_RESPONSES)
        assert "company.registry.read" in combined
        assert "products.read" in combined

    def test_account_company_fields(self, settings):
        settings.STRIPE_USE_TEST_VALUES = False
        payload = mapper.build_payload(mapper.merge_responses(PROVIDER_RESPONSES))
        company = payload["account"]["company"]
        assert company["name"] == "London Coffee Roasters Ltd"
        assert company["registration_number"] == "07654321"
        assert company["tax_id"] == "GB123456789"
        assert company["address"]["country"] == "GB"
        assert payload["account"]["business_type"] == "company"
        assert payload["account"]["business_profile"]["mcc"] == "5499"

    def test_test_values_substitution(self, settings):
        settings.STRIPE_USE_TEST_VALUES = True
        payload = mapper.build_payload(mapper.merge_responses(PROVIDER_RESPONSES))
        assert payload["account"]["company"]["tax_id"] == mapper.TEST_TAX_ID
        assert all(p["id_number"] == mapper.TEST_ID_NUMBER for p in payload["persons"])
        assert all(p["dob"] == mapper.TEST_DOB for p in payload["persons"])

    def test_persons_from_ownership(self, settings):
        settings.STRIPE_USE_TEST_VALUES = False
        payload = mapper.build_payload(mapper.merge_responses(PROVIDER_RESPONSES))
        persons = payload["persons"]
        assert len(persons) == 2
        eleanor = persons[0]
        assert eleanor["first_name"] == "Eleanor"
        assert eleanor["relationship"]["percent_ownership"] == 80
        assert eleanor["relationship"]["owner"] is True
        assert eleanor["relationship"]["representative"] is True

    def test_collected_has_provenance(self):
        payload = mapper.build_payload(mapper.merge_responses(PROVIDER_RESPONSES))
        sources = {c["source"] for c in payload["collected"]}
        assert any("Government" in s for s in sources)
        assert "Company Agent" in sources


class TestStripeServiceStub:
    """Without a Stripe key the service returns a deterministic stub."""

    def test_stub_when_no_key(self, settings):
        settings.STRIPE_SECRET_KEY = ""
        payload = mapper.build_payload(mapper.merge_responses(PROVIDER_RESPONSES))
        result = service.create_connected_account(payload)
        assert result["stub"] is True
        assert result["stripe_account_id"].startswith("acct_")
        assert result["requirements"]["currently_due"] == []
