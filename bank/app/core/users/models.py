from decimal import Decimal

from django.contrib.auth.models import AbstractUser
from django.contrib.sessions.models import Session
from faker import Faker

from app import managers, models
from app.utils.authentication import login_session

from .managers import UserManager

PROFILE_PERSON = "person"
PROFILE_BUSINESS = "business"
PROFILE_TYPES = (
    (PROFILE_PERSON, "Personal"),
    (PROFILE_BUSINESS, "Business"),
)


class User(
    AbstractUser,
    models.AppModel,
):
    """
    Custom user model for the Bank provider.

    Regular users are created via QR-code login and seeded with a synthetic
    bank account (iban, balance, currency) and a handful of historical
    movements by ``seed_profile()``. Account managers are created by
    superusers.
    """

    SYSTEM_ID = "00000000-0000-0000-0000-000000000000"

    email = models.EmailField(unique=True, null=True)
    permyt_user_id = models.UUIDField(unique=True, db_index=True, null=True)

    is_account_manager = models.BooleanField(default=False)

    # Personal vs business account — chosen at login (QR). A business account
    # asks the government provider for the COMPANY's legal name + registered
    # address rather than a person's name (the broker's scope picker isn't
    # smart enough yet to infer this from the description alone).
    profile_type = models.CharField(
        max_length=16, choices=PROFILE_TYPES, default=PROFILE_PERSON, db_index=True
    )

    full_name = models.CharField(max_length=255, blank=True, default="")
    address = models.CharField(max_length=512, blank=True, default="")
    birthdate = models.CharField(max_length=32, blank=True, default="")
    iban = models.CharField(max_length=34, blank=True, default="")
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, blank=True, default="EUR")

    # PERMYT requester onboarding — the bank requests the new account
    # holder's verified identity (name + address + birthdate) from the
    # government provider after connect. ``onboarding_request_id`` holds the
    # in-flight access request; ``onboarding_complete`` flips once the
    # verified identity has been written onto the account.
    onboarding_request_id = models.CharField(max_length=64, blank=True, default="")
    onboarding_complete = models.BooleanField(default=False)

    # Compliance signals the bank answers directly for KYC requesters:
    # where the account is funded from, an affordability band, and whether any
    # gambling-harm flag is set. Seeded to a clean/passing state on connect.
    source_of_funds = models.CharField(max_length=255, blank=True, default="")
    disposable_income_band = models.CharField(max_length=64, blank=True, default="")
    gambling_harm = models.BooleanField(default=False)

    objects = UserManager()

    REQUIRED_FIELDS = []
    USERNAME_FIELD = "email"
    DELETED_USERNAME = "deleted-user"

    @property
    def is_business(self) -> bool:
        return self.profile_type == PROFILE_BUSINESS

    def __str__(self):
        return self.email or str(self.pk)

    def save(self, *args, **kwargs):
        self.iban = (self.iban or "").replace(" ", "").replace("-", "").upper()
        self.currency = (self.currency or "EUR").upper()
        super().save(*args, **kwargs)

    def seed_profile(self):
        """Seed the synthetic *banking* data the bank owns itself: an IBAN,
        a starting balance, the base currency, and a handful of historical
        movements.

        The account holder's identity — ``full_name``, ``address``, and
        ``birthdate`` — is deliberately NOT faked here. It is fetched from
        the government provider over PERMYT during onboarding (see
        ``PermytClient.process_user_connect`` →
        ``_handle_identity_completion``) so the dashboard shows a verified
        identity rather than a made-up name.

        Idempotent: pre-set values are preserved, so dashboard edits aren't
        clobbered if ``user_connect`` fires again. Movements are seeded only
        on the very first call (when the user has none yet).
        """
        # pylint: disable=import-outside-toplevel
        from app.core.bank.seed import seed_movements

        fake = Faker("en_GB")

        if not self.iban:
            self.iban = fake.iban()
        if not self.currency:
            self.currency = "EUR"
        if self.balance in (None, Decimal("0")):
            self.balance = Decimal(fake.random_int(min=1500, max=12000))
        if not self.source_of_funds:
            self.source_of_funds = "salary, accumulated over ~18 months"
        if not self.disposable_income_band:
            self.disposable_income_band = "£500–£1,000/month"

        self.save()

        if not self.movements.exists():
            seed_movements(self)


class LoginToken(models.AppModel):
    """
    This stores the QR Code token generated when logging in users.
    Since we are using QR code login, the only way to have already authenticated user
    is if the user is an account manager, created by superuser. Otherwise, the user
    will always be null.
    """

    WEBSOCKET_NOTIFICATIONS_ENABLED = False
    DELETE_AFTER = 5 * 60  # in minutes, to allow for cleanup after use

    token = models.CharField(max_length=2048, unique=True)
    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE, related_name="login_tokens")
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="login_tokens")
    logged_in = models.BooleanField(default=False)
    # Personal/Business choice the visitor made on the login page, applied to
    # the account on connect so onboarding requests the right identity.
    profile_type = models.CharField(max_length=16, choices=PROFILE_TYPES, default=PROFILE_PERSON)
    objects = managers.SuperuserManager(superuser_field="is_account_manager")

    def login(self, user: User):
        """Mark this token as used for login (after the user has scanned the QR code)."""
        if self.logged_in:
            raise ValueError("This token has already been used for login.")

        if self.user and self.user != user:
            raise ValueError("This token is associated with a different user.")

        login_session(session=self.session, user=user)
        self.user = user
        self.logged_in = True
        self.save()
