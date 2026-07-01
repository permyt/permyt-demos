import re

from django.contrib.auth.models import AbstractUser
from django.contrib.sessions.models import Session
from faker import Faker

from app import managers, models
from app.utils.authentication import login_session

from .managers import UserManager

PHONE_E164_RE = re.compile(r"^\+\d{6,15}$")

PROFILE_PERSON = "person"
PROFILE_BUSINESS = "business"
PROFILE_TYPES = (
    (PROFILE_PERSON, "Person"),
    (PROFILE_BUSINESS, "Business"),
)


class User(
    AbstractUser,
    models.AppModel,
):
    """
    Custom user model for the Government provider.

    Regular users are created via QR-code login and seeded with a synthetic
    citizen profile (full_name, birthdate, address, country, vat, phone, email,
    tax_id) by ``seed_profile()``.
    Account managers are created by superusers.
    """

    SYSTEM_ID = "00000000-0000-0000-0000-000000000000"

    email = models.EmailField(unique=True, null=True)
    permyt_user_id = models.UUIDField(unique=True, db_index=True, null=True)

    is_account_manager = models.BooleanField(default=False)

    # Discriminates a citizen (person) record from a company (business) record.
    # Persons expose the 8 citizen profile cols below; businesses expose the
    # related ``BusinessProfile`` + ``Shareholder`` rows via the ``company.*`` scopes.
    profile_type = models.CharField(
        max_length=16, choices=PROFILE_TYPES, default=PROFILE_PERSON, db_index=True
    )

    full_name = models.CharField(max_length=255, blank=True, default="")
    birthdate = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True, default="")
    country = models.CharField(max_length=2, blank=True, default="")
    vat = models.CharField(max_length=64, blank=True, default="")
    phone = models.CharField(max_length=32, blank=True, default="")
    tax_id = models.CharField(max_length=64, blank=True, default="")
    # National identity document numbers (synthetic in this demo).
    passport_number = models.CharField(max_length=16, blank=True, default="")
    social_security_number = models.CharField(max_length=16, blank=True, default="")
    citizen_card_number = models.CharField(max_length=16, blank=True, default="")

    # Identity / right-to-work / driving-licence standing, answered directly by
    # the national register. Defaults are the "passing" state so a freshly
    # connected citizen demos cleanly; editable like the rest of the profile.
    identity_verified = models.BooleanField(default=True)
    right_to_work = models.BooleanField(default=True)
    right_to_work_type = models.CharField(max_length=64, blank=True, default="")
    driving_licence_valid = models.BooleanField(default=True)
    driving_licence_categories = models.CharField(max_length=64, blank=True, default="")
    driving_licence_disqualified = models.BooleanField(default=False)
    driving_licence_points_band = models.CharField(max_length=16, blank=True, default="")

    objects = UserManager()

    REQUIRED_FIELDS = []
    USERNAME_FIELD = "email"
    DELETED_USERNAME = "deleted-user"

    def __str__(self):
        return self.email or str(self.pk)

    @property
    def is_business(self) -> bool:
        return self.profile_type == PROFILE_BUSINESS

    @property
    def is_connected(self) -> bool:
        return self.permyt_user_id is not None

    def save(self, *args, **kwargs):
        self.country = (self.country or "").upper()
        super().save(*args, **kwargs)

    def seed(self):
        """Type-aware seeding — fills blanks for the right profile type."""
        if self.is_business:
            self.seed_business()
        else:
            self.seed_profile()

    def seed_business(self):
        """Ensure a business record has a ``BusinessProfile`` with synthetic
        blanks filled. Idempotent — pre-set values are preserved."""
        profile, _ = BusinessProfile.objects.get_or_create(user=self)
        profile.seed()

    def seed_profile(self):
        """Fill any blank profile fields with synthetic Faker data.

        Idempotent: pre-set values are preserved, so dashboard edits aren't
        clobbered if ``user_connect`` fires again.
        """
        if self.is_business:
            self.seed_business()
            return
        fake = Faker()
        country = (self.country or fake.country_code(representation="alpha-2")).upper()

        if not self.full_name:
            self.full_name = fake.name()
        if not self.birthdate:
            self.birthdate = fake.date_of_birth(minimum_age=25, maximum_age=75)
        if not self.address:
            self.address = fake.address()
        if not self.country:
            self.country = country
        if not self.vat:
            self.vat = f"{country}{fake.numerify('#########')}"
        if not self.tax_id:
            self.tax_id = fake.numerify("###-##-####")
        if not self.phone:
            raw = re.sub(r"[^\d+]", "", fake.phone_number())
            if not raw.startswith("+"):
                raw = "+1" + raw.lstrip("0")
            if not PHONE_E164_RE.match(raw):
                raw = "+1" + fake.numerify("##########")
            self.phone = raw
        if not self.passport_number:
            self.passport_number = fake.bothify("?######").upper()
        if not self.social_security_number:
            self.social_security_number = fake.numerify("###-##-####")
        if not self.citizen_card_number:
            self.citizen_card_number = fake.numerify("########")
        if not self.right_to_work_type:
            self.right_to_work_type = "settled status"
        if not self.driving_licence_categories:
            self.driving_licence_categories = "B"
        if not self.driving_licence_points_band:
            self.driving_licence_points_band = "0-3"

        self.save()


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
    # For browser-login QRs (no pre-created ``user``), this records the
    # Personal/Business choice the visitor made on the landing page so the
    # freshly-created record gets the right ``profile_type``.
    profile_type = models.CharField(max_length=16, choices=PROFILE_TYPES, default=PROFILE_PERSON)
    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE, related_name="login_tokens")
    # Browser-login QRs bind to a session (so the scanning logs that browser in).
    # Registration QRs bind to a pre-created ``user`` record and have no session —
    # scanning links the scanner's PERMYT profile to that record (no browser login).
    session = models.ForeignKey(
        Session, null=True, blank=True, on_delete=models.CASCADE, related_name="login_tokens"
    )
    logged_in = models.BooleanField(default=False)
    # Set when a scan is rejected (e.g. the scanned profile is a different
    # account type than the visitor selected) so the polling page can show it.
    error = models.CharField(max_length=255, blank=True, default="")
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


# Coffee-roaster MCC (5499 = Misc Food Stores) — used as the business seed default.
DEFAULT_MCC = "5499"

BUSINESS_STRUCTURES = (
    ("private_corporation", "Private corporation"),
    ("private_partnership", "Private partnership"),
    ("public_corporation", "Public corporation"),
    ("sole_proprietorship", "Sole proprietorship"),
)


class BusinessProfile(models.AppModel):
    """Authoritative company registry + tax record for a business ``User``.

    Companies-House-style registry data (legal name, registration number,
    incorporation date, structure) plus HMRC-style tax id, exposed via the
    ``company.*`` scopes. Beneficial owners live in related ``Shareholder``
    rows and carry the KYC the Stripe persons API needs.
    """

    WEBSOCKET_NOTIFICATIONS_ENABLED = False

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="business_profile")
    legal_name = models.CharField(max_length=255, blank=True, default="")
    registration_number = models.CharField(max_length=64, blank=True, default="", db_index=True)
    tax_id = models.CharField(max_length=64, blank=True, default="")
    incorporation_date = models.DateField(null=True, blank=True)
    registered_address = models.TextField(blank=True, default="")
    country = models.CharField(max_length=2, blank=True, default="")
    structure = models.CharField(
        max_length=32, choices=BUSINESS_STRUCTURES, blank=True, default="private_corporation"
    )
    mcc = models.CharField(max_length=4, blank=True, default="")
    website = models.CharField(max_length=255, blank=True, default="")

    objects = managers.SuperuserManager()

    def __str__(self):
        return self.legal_name or str(self.pk)

    def save(self, *args, **kwargs):
        self.country = (self.country or "").upper()
        super().save(*args, **kwargs)

    def seed(self):
        """Fill blank registry/tax fields with synthetic data. Idempotent."""
        fake = Faker("en_GB")
        country = (self.country or "GB").upper()

        if not self.legal_name:
            self.legal_name = (
                f"{fake.last_name()} {fake.random_element(('Ltd', 'Holdings Ltd', 'Trading Ltd'))}"
            )
        if not self.registration_number:
            self.registration_number = fake.numerify("########")
        if not self.tax_id:
            self.tax_id = fake.numerify("##########")
        if not self.incorporation_date:
            self.incorporation_date = fake.date_between(start_date="-20y", end_date="-1y")
        if not self.registered_address:
            self.registered_address = fake.address()
        if not self.country:
            self.country = country
        if not self.mcc:
            self.mcc = DEFAULT_MCC
        if not self.website:
            # Avoid example.com/.test — Stripe (and other consumers) reject
            # reserved/documentation domains as invalid URLs.
            slug = re.sub(r"[^a-z0-9]+", "", self.legal_name.lower()) or "company"
            self.website = f"https://www.{slug}.com"

        self.save()

        # Ensure at least one beneficial owner exists for a credible KYB demo.
        if not self.shareholders.exists():
            Shareholder.objects.create(
                business=self,
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                ownership_percent=100,
                is_representative=True,
                is_director=True,
            ).seed()


class Shareholder(models.AppModel):
    """A beneficial owner / officer of a ``BusinessProfile``.

    Carries the KYC facts (name, DOB, address, id number, ownership %) that the
    single-approver onboarding flow surfaces via ``company.ownership.read`` and
    ``company.officers.read``.
    """

    WEBSOCKET_NOTIFICATIONS_ENABLED = False

    business = models.ForeignKey(
        BusinessProfile, on_delete=models.CASCADE, related_name="shareholders"
    )
    first_name = models.CharField(max_length=128, blank=True, default="")
    last_name = models.CharField(max_length=128, blank=True, default="")
    birthdate = models.DateField(null=True, blank=True)
    address = models.TextField(blank=True, default="")
    country = models.CharField(max_length=2, blank=True, default="")
    id_number = models.CharField(max_length=64, blank=True, default="")
    ownership_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    title = models.CharField(max_length=128, blank=True, default="")
    is_representative = models.BooleanField(default=False)
    is_director = models.BooleanField(default=False)

    objects = managers.SuperuserManager()

    class Meta:
        ordering = ("-ownership_percent",)

    def __str__(self):
        return f"{self.first_name} {self.last_name} ({self.ownership_percent}%)"

    def save(self, *args, **kwargs):
        self.country = (self.country or "").upper()
        super().save(*args, **kwargs)

    def seed(self):
        """Fill blank KYC fields with synthetic data. Idempotent."""
        fake = Faker("en_GB")
        if not self.first_name:
            self.first_name = fake.first_name()
        if not self.last_name:
            self.last_name = fake.last_name()
        if not self.birthdate:
            self.birthdate = fake.date_of_birth(minimum_age=30, maximum_age=70)
        if not self.address:
            self.address = fake.address()
        if not self.country:
            self.country = (self.business.country or "GB").upper()
        if not self.id_number:
            self.id_number = fake.numerify("#########")
        if not self.title:
            self.title = "Director" if self.is_director else "Officer"
        self.save()
