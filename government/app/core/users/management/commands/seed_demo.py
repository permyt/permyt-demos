"""Seed the Government provider with the Permyt × Stripe workshop demo data.

Creates the authoritative records used by the workshop:
  * London Coffee Roasters Ltd (business) — UK registry + tax + 2 beneficial owners
  * Eleanor Pembroke (80%) and James Hartley (20%)
  * A sample citizen (person) record

Idempotent — re-running updates the existing records in place. Records start
unlinked (no ``permyt_user_id``); connect them via the registry QR.

Usage::

    python manage.py seed_demo
"""

from datetime import date

from django.core.management.base import BaseCommand

from app.core.users.models import (
    PROFILE_BUSINESS,
    PROFILE_PERSON,
    BusinessProfile,
    Shareholder,
    User,
)


class Command(BaseCommand):
    help = "Seed the Permyt × Stripe workshop demo data (London Coffee Roasters Ltd)."

    def handle(self, *args, **options):
        business = self._seed_business()
        self._seed_person()
        self.stdout.write(self.style.SUCCESS("Seeded workshop demo data."))
        self.stdout.write(
            f"  Business record id: {business.id} (connect via /register/{business.id}/)"
        )

    def _seed_business(self) -> User:
        user, _ = User.objects.get_or_create(
            username="business-07654321",
            defaults={"profile_type": PROFILE_BUSINESS},
        )
        user.profile_type = PROFILE_BUSINESS
        user.save(update_fields=["profile_type"])

        biz, _ = BusinessProfile.objects.update_or_create(
            user=user,
            defaults={
                "legal_name": "London Coffee Roasters Ltd",
                "registration_number": "07654321",
                "tax_id": "GB123456789",
                "incorporation_date": date(2015, 6, 15),
                "registered_address": "42 Brick Lane, London E1 6QL",
                "country": "GB",
                "structure": "private_corporation",
                "mcc": "5499",
                "website": "https://londoncoffeeroasters.com",
            },
        )

        owners = [
            {
                "first_name": "Eleanor",
                "last_name": "Pembroke",
                "birthdate": date(1972, 3, 12),
                "address": "10 Clerkenwell Road, London EC1M 5QA",
                "country": "GB",
                "id_number": "PEMB720312",
                "ownership_percent": 80,
                "title": "Managing Director",
                "is_representative": True,
                "is_director": True,
            },
            {
                "first_name": "James",
                "last_name": "Hartley",
                "birthdate": date(1978, 7, 5),
                "address": "22 Shoreditch High St, London E1 6PG",
                "country": "GB",
                "id_number": "HART780705",
                "ownership_percent": 20,
                "title": "Director",
                "is_representative": False,
                "is_director": True,
            },
        ]
        for o in owners:
            Shareholder.objects.update_or_create(
                business=biz,
                first_name=o["first_name"],
                last_name=o["last_name"],
                defaults={k: v for k, v in o.items() if k not in ("first_name", "last_name")},
            )
        return user

    def _seed_person(self) -> User:
        user, _ = User.objects.get_or_create(
            username="person-eleanor",
            defaults={"profile_type": PROFILE_PERSON},
        )
        user.profile_type = PROFILE_PERSON
        user.full_name = "Eleanor Pembroke"
        user.birthdate = date(1972, 3, 12)
        user.address = "10 Clerkenwell Road, London EC1M 5QA"
        user.country = "GB"
        user.vat = "GB123456789"
        user.tax_id = "PEMB720312"
        if not user.phone:
            user.phone = "+442079460001"
        if not user.email:
            user.email = "eleanor@londoncoffeeroasters.com"
        user.save()
        return user
