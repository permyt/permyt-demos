from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db.models import QuerySet

from app.managers import OwnerManager
from app.permissions import PermissionType


class UserManager(OwnerManager, DjangoUserManager):
    """Plumbing-only — the hotel demo never authenticates anyone."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("field", "id")
        kwargs.setdefault("only_superusers_can_create", True)
        super().__init__(*args, **kwargs)

    def create_user(self, username, email=None, password=None, **extra_fields):
        return self._create_user(email, email=email, password=password, **extra_fields)

    def create_superuser(self, email=None, password=None, **extra_fields):
        return super().create_superuser(email, email=email, password=password, **extra_fields)

    def with_permission(
        self, user, permission: PermissionType, as_superuser=False, **kwargs
    ) -> QuerySet:
        if as_superuser and self.is_superuser(user):
            return self.get_queryset()
        return self.get_queryset().none()
