"""Seed the Company-Agent provider with the workshop company knowledge base.

Creates the "London Coffee Roasters Ltd" company record + KB used by the
Permyt × Stripe workshop. Idempotent. The record starts unlinked — connect it
via the registry QR.

Usage::

    python manage.py seed_demo
"""

from django.core.management.base import BaseCommand

from app.core.users.models import CompanyKB, User

BUSINESS_PLAN = (
    "London Coffee Roasters Ltd is a speciality coffee roaster based in East London, "
    "sourcing single-origin green beans directly from cooperatives in Ethiopia, Colombia "
    "and Guatemala. The company sells through three channels: a wholesale programme for "
    "independent cafes, a direct-to-consumer subscription, and a flagship roastery cafe. "
    "Growth strategy for the next 18 months centres on expanding wholesale accounts across "
    "the UK and launching nationwide subscription fulfilment, funded by Stripe Treasury payouts."
)

FINANCIALS = (
    "FY2025 revenue £1.8M, up 34% YoY. Gross margin 58%. Wholesale is 60% of revenue, "
    "subscriptions 28%, cafe 12%. Positive operating cash flow; ~7 months runway in reserve. "
    "Seeking to enable Treasury payouts to settle wholesale receivables faster."
)

PRODUCTS = [
    "Single-origin whole-bean coffee (250g / 1kg)",
    "Wholesale roasting & private-label programme",
    "Monthly subscription boxes",
    "Barista training workshops",
]


class Command(BaseCommand):
    help = "Seed the workshop company knowledge base (London Coffee Roasters Ltd)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--extra",
            type=int,
            default=3,
            help="How many additional synthetic demo companies to seed (default 3).",
        )

    def handle(self, *args, **options):
        user, _ = User.objects.get_or_create(username="company-london-coffee")
        CompanyKB.objects.update_or_create(
            user=user,
            defaults={
                "name": "London Coffee Roasters Ltd",
                "business_plan": BUSINESS_PLAN,
                "financials_summary": FINANCIALS,
                "products": PRODUCTS,
                "narrative": (
                    "UK-registered (Companies House 07654321). Owners: Eleanor Pembroke (80%), "
                    "James Hartley (20%). MCC 5499. Onboarding to a Stripe Connect marketplace "
                    "for Treasury payouts."
                ),
            },
        )
        self.stdout.write(self.style.SUCCESS("Seeded workshop company knowledge base."))
        self.stdout.write(f"  Company record id: {user.id} (connect via /register/{user.id}/)")

        # A few extra synthetic companies so the registry has realistic variety.
        # CompanyKB.seed() fills every blank field with believable Faker content.
        extra = options.get("extra") or 0
        for _ in range(extra):
            company = User.objects.create(username=f"company-{User.objects.count()}")
            kb = CompanyKB.objects.create(user=company)
            kb.seed()
            self.stdout.write(f"  Seeded synthetic company: {kb.name} ({company.id})")
