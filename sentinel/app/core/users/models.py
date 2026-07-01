from django.contrib.auth.models import AbstractUser
from django.contrib.sessions.models import Session

from app import managers, models
from app.utils.authentication import login_session

from .managers import UserManager


class User(
    AbstractUser,
    models.AppModel,
):
    """
    Custom user model for the Sentinel Screening provider.

    Sentinel is a compliance-grade watchlist authority. Each connected subject
    has a screening record answering four boolean checks: sanctions match, PEP
    status, adverse-media, and gambling self-exclusion. Records are created via
    QR-code login and seeded **clear** (no match / not excluded) by
    ``seed_profile()`` so a freshly connected subject demos cleanly. The status
    is editable from the dashboard so denials can be demonstrated too.
    """

    SYSTEM_ID = "00000000-0000-0000-0000-000000000000"

    email = models.EmailField(unique=True, null=True)
    permyt_user_id = models.UUIDField(unique=True, db_index=True, null=True)

    is_account_manager = models.BooleanField(default=False)

    # Screening outcomes, answered directly to KYC requesters. Defaults are the
    # "clear" state — a connected subject passes screening unless flagged.
    sanctions_match = models.BooleanField(default=False)
    pep = models.BooleanField(default=False)
    adverse_media = models.BooleanField(default=False)
    self_excluded = models.BooleanField(default=False)

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
        """Alias kept for parity with the other providers' connect hook."""
        self.seed_profile()

    def seed_profile(self):
        """Ensure the screening record exists. The four outcomes default to the
        clear state, so there is nothing to fake — this just persists the row.

        Idempotent: dashboard edits (e.g. flipping a flag to demo a denial) are
        preserved if ``user_connect`` fires again.
        """
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
    user = models.ForeignKey(User, null=True, on_delete=models.CASCADE, related_name="login_tokens")
    # Browser-login QRs bind to a session (so the scanning logs that browser in).
    session = models.ForeignKey(
        Session, null=True, blank=True, on_delete=models.CASCADE, related_name="login_tokens"
    )
    logged_in = models.BooleanField(default=False)
    # Set when a scan is rejected so the polling page can show it.
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
