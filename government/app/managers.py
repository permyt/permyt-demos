from __future__ import annotations

from django.db.models import Manager, QuerySet

from .permissions import PERMISSIONS, PermissionType


class BaseManager(Manager):
    """
    Base Manager containing all common methods for all managers in PFT.

    Managers should only retrieve from database the data user should have access.
    The goal is to make this filtering automatically from viewsets and others
    to avoid security issues.

    Examples:
        Model.objects.as_reader(): Return all objects user has permissions as reader.
        Model.objects.as_writer(): Return all objects user has permissions as writer.
    """

    def __init__(
        self,
        *args,
        public: bool = False,
        allow_guests: bool = False,
        estimate_count: bool = False,
        only_superusers_can_create: bool = False,
        superuser_field: list[str] | str = "is_superuser",
        **kwargs,
    ):
        """
        :param estimate_count: Estimate count instead of counting elements for speed
        """
        super().__init__(*args, **kwargs)
        self.only_superusers_can_create = only_superusers_can_create
        self.estimate_count = estimate_count
        self._superuser_field = (
            [superuser_field] if isinstance(superuser_field, str) else superuser_field
        )
        self._public = public
        self._allow_guests = allow_guests

    def with_permission(self, user, permission: PermissionType, **kwargs) -> QuerySet:
        """
        Returns a queryset based on user and permission.

        This method must be overridden by all other managers
        """
        raise NotImplementedError(f"`with_permission` is not defined in {self.__class__.__name__}")

    def as_reader(self, user, **kwargs) -> QuerySet:
        """
        Returns only the data user have permissions to read.
        """
        return self.with_permission(user, PERMISSIONS.READ, **kwargs)

    def as_writer(self, user, **kwargs) -> QuerySet:
        """
        Returns only the data user have permissions to write.
        """
        kwargs.setdefault("as_superuser", True)
        return self.with_permission(user, PERMISSIONS.WRITE, **kwargs)

    def as_admin(self, user, **kwargs) -> QuerySet:
        """
        Returns only the data user have permissions as admin.
        """
        kwargs.setdefault("as_superuser", True)
        return self.with_permission(user, PERMISSIONS.ADMIN, **kwargs)

    def as_owner(self, user, **kwargs) -> QuerySet:
        """
        Returns only the data user have permissions as owner.
        """
        return self.with_permission(user, PERMISSIONS.OWNER, **kwargs)

    def check_object_permission(self, obj, user, permission) -> bool:
        """
        Check if user have a specific permission for an object
        """
        raise NotImplementedError(
            f"`check_object_permission` is not defined in {self.__class__.__name__}"
        )

    def is_superuser(self, user) -> bool:
        """Check if user is superuser"""
        return user.is_superuser or any(
            getattr(user, field, False) for field in self._superuser_field
        )

    def can_create(self, user) -> bool:
        """Check if user can create objects"""
        return user.is_authenticated and (
            not self.only_superusers_can_create or self.is_superuser(user)
        )


class SuperuserManager(BaseManager):
    """
    All objects from models containing this manager can only be created
    and changed by superusers. If they are set as public, all users can
    list and view the objects.
    """

    def __init__(self, *args, **kwargs):
        """
        :param public: If data is accessible to all users as readers
        """
        kwargs.setdefault("only_superusers_can_create", True)
        kwargs.setdefault("public", False)
        super().__init__(*args, **kwargs)

    def with_permission(self, user, permission: PermissionType, **kwargs) -> QuerySet:
        """
        Returns a queryset based on user and permission.

        Only superusers can access data.
        """
        # Superusers have always access and public objects are accessible to everyone
        if (self._public and permission == PERMISSIONS.READ) or self.is_superuser(user):
            return self.get_queryset()

        return self.get_queryset().none()

    def check_object_permission(self, obj, user, permission) -> bool:
        """
        Check if user have a specific permission for an object.

        Only superusers have permissions on the object.
        """
        return self.is_superuser(user) or (self._public and permission == PERMISSIONS.READ)


class PublicReadManager(SuperuserManager):
    """
    All objects from models containing this manager can be read by all users.
    Only superusers can create and change the objects.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("public", True)
        super().__init__(*args, **kwargs)


class OwnerManager(SuperuserManager):
    """
    Models containing this manager, only owner (creator) and superusers
    can edit or delete objects. Other users can read if manager define
    objects as public.

    :param field: Field that identifies owner in the model
    :param public: If true, all users have access to data as reader
    """

    def __init__(self, *args, field: str = "created_by", **kwargs):
        kwargs.setdefault("only_superusers_can_create", False)
        kwargs.setdefault("public", False)
        self._field = field

        super().__init__(*args, **kwargs)

    def with_permission(
        self, user, permission: PermissionType, as_superuser=False, **kwargs
    ) -> QuerySet:
        """
        Returns a queryset based on user and permission.

        Owners (creators) can write. All other users can only read.
        """

        # Owner have always access and public objects are accessible to everyone
        if (permission == PERMISSIONS.READ and self._public) or (
            as_superuser and self.is_superuser(user)
        ):
            return self.get_queryset()

        # Otherwise, only owner should have access to it
        return self.get_queryset().filter(**{self._field: user.pk})

    def check_object_permission(self, obj, user, permission) -> bool:
        """
        Check if user have a specific permission for an object.

        Only owner can write on the object, all others can read.
        """

        # Owners have always access and public objects are accessible to everyone
        if (permission == PERMISSIONS.READ and self._public) or self.is_superuser(user):
            return True

        model = obj.__class__
        return model.objects.with_permission(user, permission).filter(id=obj.id).exists()
