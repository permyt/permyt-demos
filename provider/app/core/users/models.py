import random

from django.contrib.auth.models import AbstractUser
from django.contrib.sessions.models import Session

from app import managers, models
from app.utils.authentication import login_session

from .managers import UserManager

SEED_TEXTS = [
    "Day 1: Launched from Baikonur at 0342 UTC. Stage separation nominal. Orbital insertion confirmed — altitude 408 km, inclination 51.6 degrees.",
    "Lat: 28.5721° N, Lon: 80.6480° W — Kennedy Space Center, Launch Complex 39A. Elevation: 8m ASL.",
    "Commander Vasquez reports intermittent tinnitus in left ear — likely cabin pressure fluctuation during last EVA.",
    "PRIORITY: ROUTINE. Ground, this is Orbital-7. Telemetry nominal all channels. Request updated TLE set for debris avoidance manoeuvre.",
    "EVA-3 complete. Replaced degraded thermal blanket on port truss segment S4. Total EVA time: 6 hours 22 minutes.",
    "RA 05h 34m 31.94s, Dec +22° 00' 52.2\" — Crab Nebula (M1). Distance: 6,523 ± 26 light-years.",
    "Transit day 47. Mid-course correction burn executed — delta-v 2.3 m/s. Communication latency at 14 minutes and increasing.",
    "BROADCAST: All stations. Solar storm warning — NOAA class X2.1 flare detected 0312 UTC. Shelter protocols recommended.",
]


class User(
    AbstractUser,
    models.AppModel,
):
    """
    Custom user model for the NoteVault provider.

    Regular users are created via QR-code login.
    Account managers are created by superusers.
    """

    SYSTEM_ID = "00000000-0000-0000-0000-000000000000"

    email = models.EmailField(unique=True, null=True)
    permyt_user_id = models.UUIDField(unique=True, db_index=True, null=True)

    is_account_manager = models.BooleanField(default=False)

    # Custom model manager with project-specific helpers.
    objects = UserManager()

    REQUIRED_FIELDS = []
    USERNAME_FIELD = "email"
    DELETED_USERNAME = "deleted-user"

    def __str__(self):
        return self.email or str(self.pk)

    def seed_field_values(self):
        """Create a UserFieldValue for every NoteField that this user lacks."""
        existing = set(self.field_values.values_list("field__slug", flat=True))
        missing = NoteField.objects.exclude(slug__in=existing)
        UserFieldValue.objects.bulk_create(
            [
                UserFieldValue(
                    user=self,
                    field=nf,
                    value=random.choice(SEED_TEXTS),
                )
                for nf in missing
            ],
            ignore_conflicts=True,
        )


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


class NoteField(models.AppModel):
    """Global field definition. Superusers create/delete these; each generates two scopes."""

    WEBSOCKET_NOTIFICATIONS_ENABLED = False

    slug = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=128)

    objects = managers.SuperuserManager(public=True)

    class Meta:
        ordering = ("created_at",)

    def __str__(self):
        return str(self.slug)


class UserFieldValue(models.AppModel):
    """Per-user value for a NoteField."""

    WEBSOCKET_NOTIFICATIONS_ENABLED = False

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="field_values")
    field = models.ForeignKey(NoteField, on_delete=models.CASCADE, related_name="values")
    value = models.TextField(default="", blank=True)

    objects = managers.OwnerManager(field="user")

    class Meta:
        unique_together = ("user", "field")
        ordering = ("field__created_at",)

    def __str__(self):
        return f"{self.user} / {self.field.slug}"
