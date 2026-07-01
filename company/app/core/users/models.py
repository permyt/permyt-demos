from django.contrib.auth.models import AbstractUser
from django.contrib.sessions.models import Session
from faker import Faker

from app import managers, models
from app.utils.authentication import login_session

from .managers import UserManager

# ── Synthetic-data vocabularies for CompanyKB.seed() ──────────────────
# Plain data tables (not helper functions) used to vary generated KBs.
SECTORS = (
    "B2B SaaS",
    "speciality manufacturing",
    "logistics & fulfilment",
    "consumer goods",
    "fintech",
    "health & wellness",
    "professional services",
    "clean energy",
    "food & beverage",
)
CHANNELS = (
    "a direct sales team",
    "a self-serve online platform",
    "a wholesale partner network",
    "a direct-to-consumer subscription",
    "regional distributors",
    "an enterprise channel programme",
)
PRODUCT_TEMPLATES = (
    "{noun} Platform",
    "{noun} Subscription",
    "Managed {bsword} Service",
    "{color} Edition",
    "{noun} Pro",
    "{bsword} Analytics Suite",
    "{noun} Onboarding Programme",
    "Enterprise {bsword}",
)


class User(
    AbstractUser,
    models.AppModel,
):
    """
    Custom user model for the Company-Agent provider.

    Each connected company is one ``User`` linked to PERMYT via ``permyt_user_id``.
    Its business knowledge lives in the related ``CompanyKB`` and is exposed via
    the ``business_plan.read`` / ``financials.summary`` / ``products.read`` /
    ``company.ask`` scopes.
    """

    SYSTEM_ID = "00000000-0000-0000-0000-000000000000"

    email = models.EmailField(unique=True, null=True)
    permyt_user_id = models.UUIDField(unique=True, db_index=True, null=True)

    is_account_manager = models.BooleanField(default=False)

    # Requester-side onboarding: the company's verified identity is fetched
    # from the Gov.ID provider over PERMYT on first connect. Until that
    # request completes the dashboard shows a "Fetching…" gating screen.
    onboarding_request_id = models.CharField(max_length=64, blank=True, default="")
    onboarding_complete = models.BooleanField(default=False)

    objects = UserManager()

    REQUIRED_FIELDS = []
    USERNAME_FIELD = "email"
    DELETED_USERNAME = "deleted-user"

    def __str__(self):
        return self.email or str(self.pk)

    @property
    def is_connected(self) -> bool:
        return self.permyt_user_id is not None

    def seed(self):
        """Ensure a connected company has a ``CompanyKB`` (synthetic blanks filled)."""
        kb, _ = CompanyKB.objects.get_or_create(user=self)
        kb.seed()


class LoginToken(models.AppModel):
    """QR-code token. Browser-login tokens carry a session; registration tokens
    bind a pre-created ``user`` record (no session)."""

    WEBSOCKET_NOTIFICATIONS_ENABLED = False
    DELETE_AFTER = 5 * 60

    token = models.CharField(max_length=2048, unique=True)
    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE, related_name="login_tokens")
    session = models.ForeignKey(
        Session, null=True, blank=True, on_delete=models.CASCADE, related_name="login_tokens"
    )
    logged_in = models.BooleanField(default=False)
    objects = managers.SuperuserManager(superuser_field="is_account_manager")

    def login(self, user: User):
        if self.logged_in:
            raise ValueError("This token has already been used for login.")
        if self.user and self.user != user:
            raise ValueError("This token is associated with a different user.")
        login_session(session=self.session, user=user)
        self.user = user
        self.logged_in = True
        self.save()


class CompanyKB(models.AppModel):
    """A company's own knowledge base — the data its agent answers from.

    Structured fields back the ``*.read`` scopes; the whole record is the
    grounding context for the open-ended ``company.ask`` LLM scope.
    """

    WEBSOCKET_NOTIFICATIONS_ENABLED = False

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="company_kb")

    # Gov.ID-sourced identity — non-editable, fetched over PERMYT on first
    # connect (see PermytClient onboarding flow). Never faked by seed().
    name = models.CharField(max_length=255, blank=True, default="")
    registration_number = models.CharField(max_length=128, blank=True, default="")
    registered_address = models.TextField(blank=True, default="")
    country = models.CharField(max_length=2, blank=True, default="")

    # The company's own editable knowledge base.
    business_plan = models.TextField(blank=True, default="")
    financials_summary = models.TextField(blank=True, default="")
    products = models.JSONField(default=list, blank=True)
    narrative = models.TextField(blank=True, default="")

    objects = managers.SuperuserManager()

    def __str__(self):
        return self.name or str(self.pk)

    def seed(self):
        """Fill blank KB fields with realistic synthetic company data. Idempotent.

        Only fills blanks, so the workshop's hand-authored content (loaded by
        ``seed_demo``) and operator-entered data are never overwritten. Ad-hoc
        connected companies still expose rich, believable material to requesters
        (e.g. the Stripe KYC demo, which builds a ``product_description`` from the
        ``business_plan.read`` / ``products.read`` / ``financials.summary`` /
        ``company.ask`` scopes).

        The company's *identity* (``name`` / ``registration_number`` /
        ``registered_address`` / ``country``) is intentionally never faked here —
        it is fetched from the Gov.ID provider over PERMYT during onboarding. Only
        the company's own editable knowledge base is synthesised.
        """
        faker = Faker()
        if not self.business_plan:
            self.business_plan = self.synthetic_business_plan(self.name, faker)
        if not self.financials_summary:
            self.financials_summary = self.synthetic_financials(faker)
        if not self.products:
            self.products = self.synthetic_products(faker)
        self.save()

    @staticmethod
    def synthetic_business_plan(name: str, faker: "Faker") -> str:
        """Build a believable 2-4 sentence business plan grounded in Faker."""
        company = name or faker.company()
        catchphrase = faker.catch_phrase()
        offering = faker.bs()
        city = faker.city()
        sector = faker.random_element(SECTORS)
        channel = faker.random_element(CHANNELS)
        horizon = faker.random_element(("12", "18", "24", "36"))
        return (
            f"{company} is a {sector} company headquartered in {city}, built around "
            f"{catchphrase.lower()}. The business helps its customers {offering}, "
            f"selling primarily through {channel}. Over the next {horizon} months the "
            f"company plans to expand into adjacent markets, deepen its largest accounts, "
            f"and invest in automation to widen margins."
        )

    @staticmethod
    def synthetic_financials(faker: "Faker") -> str:
        """Build a realistic high-level financial summary."""
        revenue = faker.random_int(min=4, max=180) / 10  # 0.4M – 18.0M
        currency = faker.random_element(("£", "$", "€"))
        growth = faker.random_int(min=8, max=72)
        margin = faker.random_int(min=34, max=71)
        runway = faker.random_int(min=5, max=22)
        recurring = faker.random_int(min=20, max=78)
        return (
            f"FY2025 revenue {currency}{revenue:.1f}M, up {growth}% year over year. "
            f"Gross margin {margin}%, with {recurring}% of revenue recurring. "
            f"Operating cash flow positive; ~{runway} months of runway in reserve. "
            f"Seeking faster settlement of receivables to fund growth initiatives."
        )

    @staticmethod
    def synthetic_products(faker: "Faker") -> list[str]:
        """Build a list of 3-6 plausible product / service names."""
        count = faker.random_int(min=3, max=6)
        seen: list[str] = []
        for _ in range(count * 3):
            if len(seen) >= count:
                break
            template = faker.random_element(PRODUCT_TEMPLATES)
            name = template.format(
                noun=faker.word().capitalize(),
                bsword=faker.bs().split()[-1].capitalize(),
                color=faker.color_name(),
            )
            if name not in seen:
                seen.append(name)
        return seen

    def as_context(self) -> str:
        """Render the KB as grounding text for the LLM ``company.ask`` scope."""
        lines = [f"Company: {self.name}"]
        if self.business_plan:
            lines.append(f"\nBusiness plan:\n{self.business_plan}")
        if self.financials_summary:
            lines.append(f"\nFinancials summary:\n{self.financials_summary}")
        if self.products:
            lines.append(f"\nProducts:\n{self.products}")
        if self.narrative:
            lines.append(f"\nAdditional context:\n{self.narrative}")
        return "\n".join(lines)
