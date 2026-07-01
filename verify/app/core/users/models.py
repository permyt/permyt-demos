from django.contrib.auth.models import AbstractUser

from app import models

from .managers import UserManager


class User(
    AbstractUser,
    models.AppModel,
):
    """
    Plumbing-only User model.

    The verify demo is fully session-based — no user accounts, no login flow.
    This model exists only to satisfy ``AUTH_USER_MODEL`` (Django requires
    one, and ``AppModel`` keeps ``created_by``/``updated_by`` FKs against it).
    Rows here are inert; the demo never authenticates anyone.
    """

    SYSTEM_ID = "00000000-0000-0000-0000-000000000000"

    email = models.EmailField(unique=True, null=True)

    objects = UserManager()

    REQUIRED_FIELDS = []
    USERNAME_FIELD = "email"
    DELETED_USERNAME = "deleted-user"

    def __str__(self):
        return self.email or str(self.pk)
