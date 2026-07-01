from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Type
from uuid import UUID, uuid4

import importlib

from rest_framework.serializers import ModelSerializer
from rest_framework.viewsets import ModelViewSet

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ObjectDoesNotExist
from django.db import models
from django.db.models import Q, Field
from django.utils import timezone

from app.core.users.utils import set_delete_user
from app.managers import OwnerManager, SuperuserManager
from app.permissions import PERMISSIONS
from app.tasks import (
    RunTask,
    on_post_save_background,
    on_post_delete_background,
    run_class_method_on_background,
)
from app.utils.middleware import get_current_user
from app.utils.models import run_class_method
from app.utils.permissions import check_permissions
from app.utils.views import FakeRequest
from app.utils.websocket import send_to_websocket


class BackgroundTasksMixin:
    """
    Mixin that contains the helper methods to execute
    background tasks in Celery.
    """

    WEBSOCKET_NOTIFICATIONS_ENABLED = True
    WEBSOCKET_FIELDS_LIST = None

    # Save receivers
    pre_save_receivers: set[Callable[[list[AppModel], list[str], bool], None]] = []
    post_save_receivers: set[Callable[[list[AppModel], list[str], bool], None]] = []
    post_save_background_receivers: set[Callable[[list[AppModel], bool], None]] = []

    # Delete receivers
    pre_delete_receivers: set[Callable[[list[AppModel], list[str], bool], None]] = []
    post_delete_receivers: set[Callable[[list[AppModel], list[str], bool], None]] = []
    post_delete_background_receivers: set[Callable[[list[AppModel], bool], None]] = []

    @classmethod
    def run_background_task(cls, task, *args, **kwargs):
        """
        Executed background task in celery.

        We only have the need to execute it if there are any receivers
        for the type of task to be executed. This is called by the methods
        save, delete, bulk_create, bulk_update and bulk_delete.

        :param task: Task to be executed
        :type task: BaseTask
        """

        content_type = ContentType.objects.get_for_model(cls, for_concrete_model=False)
        user = get_current_user()
        RunTask(
            task,
            content_type.id,
            *args,
            task_user_id=str(user.pk) if user else None,
            **kwargs,
        )

    @classmethod
    def run_class_method_on_background(cls, method: Callable, *args, **kwargs):
        """
        Run a class method in background.

        :param method: Method to be executed
        :type method: Callable
        :param args: Arguments to be passed to the method
        :type args: list[Any]
        :param kwargs: Keyword arguments to be passed to the method
        :type kwargs: dict[str, Any]
        """
        content_type = ContentType.objects.get_for_model(cls, for_concrete_model=False)
        user = get_current_user()
        RunTask(
            run_class_method_on_background,
            content_type.id,
            method.__name__,
            *args,
            task_user_id=str(user.pk) if user else None,
            **kwargs,
        )

    def run_method_on_background(self, method: Callable, *args, **kwargs):
        """
        Run an method in background.

        :param method: Method to be executed
        :type method: Callable
        :param args: Arguments to be passed to the method
        :type args: list[Any]
        :param kwargs: Keyword arguments to be passed to the method
        :type kwargs: dict[str, Any]
        """
        content_type = ContentType.objects.get_for_model(self, for_concrete_model=False)
        user = get_current_user()
        RunTask(
            run_class_method_on_background,
            content_type.id,
            method.__name__,
            *args,
            self_obj=self.id,
            task_user_id=str(user.pk) if user else None,
            **kwargs,
        )

    @classmethod
    def get_websocket_channels(cls, objects: list[AppModel]) -> list[str]:
        """Get the websocket channel to send the notification to"""

        if objects:
            manager = cls.objects

            if getattr(manager, "_public", False):
                return ["all"]

            if isinstance(manager, OwnerManager):
                owner_field = getattr(manager, "_field", "created_by_id")
                user = getattr(objects[0], owner_field, None)
                if user:
                    return [f"user-{user.id}" if isinstance(user, AppModel) else f"user-{user}"]

        return []

    @classmethod
    def notify_on_post_save(
        cls,
        objects: list[AppModel],
        fields: set[str] = None,
        created: bool = False,
        **kwargs,
    ):
        """Notify users about changes in objects"""
        valid_objects = cls._get_valid_websocket_objects(objects)
        if valid_objects and cls.WEBSOCKET_NOTIFICATIONS_ENABLED:
            channels = cls.get_websocket_channels(objects)
            data = cls._get_serialized_data(objects)
            for channel in channels:
                send_to_websocket(
                    channel,
                    {
                        "action": "save",
                        "created": created,
                        "fields": fields,
                        "model": cls.__name__,
                        "app": cls._meta.app_label,
                        "data": data,
                    },
                )

    @classmethod
    def notify_custom_message(cls, channel: str | list[str], action: str, data: dict[str, Any]):
        """Notify users about changes in the objects"""
        channels = channel if isinstance(channel, list) else [channel]
        for _channel in channels:
            send_to_websocket(
                _channel,
                {
                    "action": action,
                    "model": cls.__name__,
                    "app": cls._meta.app_label,
                    "data": data,
                },
            )

    @classmethod
    def notify_user(cls, data: dict[str, Any]):
        """Notify current user about changes in the objects"""
        if cls.WEBSOCKET_NOTIFICATIONS_ENABLED:
            user = get_current_user()
            if user:
                send_to_websocket(f"user-{user.id}", data)

    @classmethod
    def notify_on_post_delete(cls, objects: list[AppModel], **kwargs):
        """Notify users about changes in the objects"""
        valid_objects = cls._get_valid_websocket_objects(objects)
        if valid_objects and cls.WEBSOCKET_NOTIFICATIONS_ENABLED:
            channels = cls.get_websocket_channels(objects)
            for channel in channels:
                send_to_websocket(
                    channel,
                    {
                        "action": "delete",
                        "model": cls.__name__,
                        "app": cls._meta.app_label,
                        "data": valid_objects,
                    },
                )

    @classmethod
    def _get_serialized_data(cls, objects: list[AppModel]) -> dict[str, Any]:
        """Serialize objects to be sent to websocket"""
        serializer = cls.get_serializer_class()
        return serializer(objects, many=True, fields_list=cls.WEBSOCKET_FIELDS_LIST).data

    @classmethod
    def _get_valid_websocket_objects(cls, objects: list[AppModel]) -> list[AppModel]:
        """
        Get objects that can be sent to websocket
        Override this method to filter objects that should be sent to websocket
        """
        return objects


class TrackedFieldsMixin:
    """
    Mixin to help track data changes in a model from the moment that is
    initialized until its destruction.
    """

    # List of fields that should be tracked if a change happen
    tracked_fields: set[str] = None
    tracked_foreign_keys: dict[str, str] = None

    @classmethod
    def set_tracked_fields(cls):
        """
        Generate tracked_fields list. This should be executed only once
        from _update_tracked_fields.
        """
        cls.tracked_fields = set()
        cls.tracked_foreign_keys = {}
        for field in cls._meta.fields:
            if getattr(field, "track", False):
                # For ForeignKeys we track only their id, not the object itself.
                if isinstance(field, models.ForeignKey):
                    field_name = f"{field.name}_id"
                    cls.tracked_foreign_keys[field.name] = field_name
                else:
                    field_name = field.name
                cls.tracked_fields.add(field_name)
        return cls.tracked_fields

    def _update_tracked_fields(self) -> None:
        """
        Updates all tracked fields.

        This function should be called on AppModel when:
        1) __init__ is executed, before any data change.
        2) save method, after all data changes have been completed and stored.
        3) refresh_from_db, when object restores data from database.
        and be the last line of AppModel save method, after all changes being completed.
        """

        # Generate tracked fields when initializing an object for first time
        if self.tracked_fields is None:
            self.tracked_fields = self.__class__.set_tracked_fields()

        self._is_new = not self.created_at
        self._old_values = {}
        for field_name in self.tracked_fields:
            if field_name in self.__dict__:
                self._old_values[field_name] = deepcopy(getattr(self, field_name))

    def get_old_value(self, field_name: str) -> Any:
        """
        Returns initial value of a tracked field.

        This is the initial value when object is initialized,
        not the previous value on database.

        :param field_name: Name of the field to return old value
        :type field_name: str
        """
        return self._old_values.get(field_name)

    def get_old_values(self):
        """
        Returns a dictionary with instance values before changes.
        """
        return self._old_values

    def field_changed(self, *field_names: str) -> bool:
        """
        Returns true if any of the fields listed in field_names has changed.

        :param field_names: List of field names to check if they have been changed.
        """
        for field_name in field_names:
            previous_value = self._old_values.get(field_name)
            if previous_value != getattr(self, field_name):
                return True
        return False

    def _get_changed_fields(self) -> list[str]:
        """
        Return a list of names from all fields that have changed
        since initialization.
        """
        return {field_name for field_name in self.tracked_fields if self.field_changed(field_name)}

    def refresh_from_db(self, *args, **kwargs):
        """
        Refresh object from the database and restore track fields value
        """
        super().refresh_from_db(*args, **kwargs)
        self._update_tracked_fields()


class BulkActionsMixin(TrackedFieldsMixin, BackgroundTasksMixin):
    """
    Mixin to help execute bulk actions and respect the DJ
    """

    BULK_BATCH_SIZE: int = None

    @classmethod
    def bulk_create(
        cls,
        instances: list[AppModel],
        ignore_conflicts: bool = False,
        batch_size: int = BULK_BATCH_SIZE,
        **kwargs,
    ) -> list:
        """
        Create instances using django bulk_create and emit v_bulk_create signal.

        :param instances: Lists of instances (without ids) that should be created.
        :param ignore_conflicts: True tells the database to ignore failure to insert
            any instance that fail constraints such as duplicate unique values
        :param batch_size: number of instances to insert in one batch
        :type batch_size: int
        NOTE: In tests, the signal is sent in foreground.
        """
        user = get_current_user()
        now = timezone.now()
        for instance in instances:
            instance.created_by = user
            instance.created_at = now
            instance.updated_by = user
            instance.updated_at = now

        if instances:
            # Because we are creating new objects,
            # changed fields should be an empty set
            changed_fields = set()

            # Execute all pre_save receivers and save new kwargs
            # to be used in post save receivers
            pre_save_kwargs = {"created": True, **kwargs}
            for func in getattr(cls, "pre_save_receivers", []):
                pre_save_kwargs.update(
                    run_class_method(func, instances, changed_fields, **pre_save_kwargs) or {}
                )

            # Perform save on database
            new_instances = cls.objects.bulk_create(
                instances, ignore_conflicts=ignore_conflicts, batch_size=batch_size
            )

            # Add old_values dict and execute all post_save receivers with it
            for func in getattr(cls, "post_save_receivers", []):
                run_class_method(func, instances, changed_fields, **pre_save_kwargs)

            # Execute all post_save_background receivers in a celery task
            cls.run_background_task(
                on_post_save_background,
                new_instances,
                changed_fields,
                **pre_save_kwargs,
            )

            return new_instances
        return []

    @classmethod
    def bulk_update(
        cls,
        instances: list[AppModel],
        fields: set[str],
        *args,
        batch_size: int = BULK_BATCH_SIZE,
        **kwargs,
    ) -> list[AppModel]:
        """
        Update instances using django bulk_update and emit v_bulk_update signal

        :param instances: Lists of instances that should be update.
        :param fields: set of fields to be updated. Others will be ignored.
        :param force: If True, don't check if data has changed.
        :param batch_size: Number of instances to be updated in one query.

        NOTE: In tests, the signal is sent in foreground.
        """
        now = timezone.now()
        user = get_current_user()
        tracked_foreign_keys = cls.tracked_foreign_keys or {}
        changed_fields = {tracked_foreign_keys.get(field, field) for field in fields}
        fields_to_save = set(fields) | {"updated_by", "updated_at"}

        instances_to_update = []
        for instance in instances:
            if instance.field_changed(*changed_fields):
                instances_to_update.append(instance)
                instance.updated_by = user
                instance.updated_at = now

        if instances_to_update:
            # Execute all pre_save receivers and save new kwargs
            # to be used in post save receivers
            pre_save_kwargs = {"created": False, **kwargs}
            for func in getattr(cls, "pre_save_receivers", []):
                pre_save_kwargs.update(
                    run_class_method(func, instances_to_update, changed_fields, **pre_save_kwargs)
                    or {}
                )

            # Perform save on database
            cls.objects.bulk_update(instances_to_update, fields_to_save, batch_size=batch_size)

            # Add old_values dict and execute all post_save receivers with it
            pre_save_kwargs.update(
                {"old_values": {str(obj.id): obj.get_old_values() for obj in instances}}
            )
            for func in getattr(cls, "post_save_receivers", []):
                run_class_method(func, instances_to_update, changed_fields, **pre_save_kwargs)

            # Execute all post_save_background receivers in a celery task
            cls.run_background_task(
                on_post_save_background,
                instances_to_update,
                changed_fields,
                **pre_save_kwargs,
            )

            return instances_to_update
        return []

    @classmethod
    def bulk_delete(
        cls,
        instances: list[AppModel],
        **kwargs,
    ) -> list[AppModel]:
        """
        Delete instances using objects.delete and emit v_bulk_delete signal

        :param instances: Lists of instances that should be deleted.
        :returns: Returns a list of instances that were deleted.

        NOTE: In tests, the signal is sent in foreground.
        """
        if instances:
            # Get list of ids of the objects to delete
            # and objects as dictionary
            ids_to_delete = []
            objs_to_delete = []
            fields = cls._meta.get_fields()
            for instance in instances:
                ids_to_delete.append(instance.id)
                objs_to_delete.append(
                    {field.name: getattr(instance, field.name, None) for field in fields}
                )

            # Execute pre_delete receivers for this class
            # to be used in post delete receivers
            pre_delete_kwargs = {**kwargs}
            for func in getattr(cls, "pre_delete_receivers", []):
                pre_delete_kwargs.update(
                    run_class_method(func, instances, **pre_delete_kwargs) or {}
                )

            # Perform delete on database.
            cls.objects.filter(id__in=ids_to_delete).delete()

            # Execute post_delete receivers for this class
            for func in getattr(cls, "post_delete_receivers", []):
                run_class_method(func, instances, **pre_delete_kwargs)

            # Execute all post_save_background receivers in a celery task
            cls.run_background_task(
                on_post_delete_background,
                objs_to_delete,
                **pre_delete_kwargs,
            )

            return instances
        return []

    @classmethod
    def bulk_add_values(
        cls,
        instances: list[AppModel],
        field_name: str,
        values: list[AppModel] | list[int],
        **kwargs,
    ) -> list[AppModel]:
        """Generic bulk action to efficiently add values to an M2M field

        The method automatically determines the reverse relation.

        :param instances: instances that should be bulk edited
        :param field: name of the field that is edited
        :param values: IDs of items that should be added
        :returns: updated instances
        """
        (
            ThroughModel,  # pylint: disable=invalid-name
            field,
            _,
            from_field_name,
            to_field_name,
        ) = cls.get_m2m_properties(instances[0], field_name)
        RelatedModel = field.related_model  # pylint: disable=invalid-name

        # From automation, the values will be the objects itself
        if values and isinstance(values[0], AppModel):
            target_objects = values
            values = [obj.id for obj in target_objects]

        # From requests the list will be ids
        else:
            # Check permissions for values in case the function was triggered by a user request.
            user = get_current_user()
            if user:
                target_objects = RelatedModel.objects.as_writer(user).filter(pk__in=values)
                check_permissions(target_objects, values)
            else:
                target_objects = RelatedModel.objects.filter(pk__in=values)

        through_instances = []
        for instance in instances:
            for value in values:
                through_instance = ThroughModel(
                    **{
                        from_field_name: instance,
                        f"{to_field_name}_id": value,
                    }
                )
                through_instances.append(through_instance)

        ThroughModel.objects.bulk_create(through_instances, ignore_conflicts=True)
        cls.objects.filter(id__in=[instance.id for instance in instances]).update(
            updated_at=timezone.now()
        )
        # Add lines below when automation are implemented
        # added = {instance.id: target_objects for instance in instances}
        # cls._common_on_m2m_change(instances, added, {}, field_name, RelatedModel)

        return instances

    @classmethod
    def bulk_remove_values(
        cls,
        instances: list[AppModel],
        field_name: str,
        values: list[AppModel] | list[int],
        **kwargs,
    ) -> list[AppModel]:
        """Generic bulk action to efficiently remove values from an M2M field

        The method automatically determines the reverse relation.

        :param instances: instances that should be bulk edited
        :param field: name of the field that is edited
        :param values: IDs of items that should be removed
        :returns: updated instances
        """
        (
            ThroughModel,  # pylint: disable=invalid-name
            field,
            _,
            from_field_name,
            to_field_name,
        ) = cls.get_m2m_properties(instances[0], field_name)
        RelatedModel = field.related_model  # pylint: disable=invalid-name

        # From automation, the values will be the objects itself
        if values and isinstance(values[0], AppModel):
            target_objects = values
            values = [obj.id for obj in target_objects]

        # From requests the list will be ids
        else:
            # From requests the list will be ids
            target_objects = RelatedModel.objects.filter(pk__in=values)

        query = Q()
        for value in values:
            query |= Q(
                **{
                    f"{from_field_name}__in": instances,
                    f"{to_field_name}_id": value,
                }
            )

        ThroughModel.objects.filter(query).delete()
        cls.objects.filter(id__in=[instance.id for instance in instances]).update(
            updated_at=timezone.now()
        )
        # Add lines below when automation are implemented
        # removed = {instance.id: target_objects for instance in instances}
        # cls._common_on_m2m_change(instances, {}, removed, field_name, RelatedModel)

        return instances

    @staticmethod
    def get_m2m_properties(instance: Any, field_name: str) -> tuple[AppModel, Field, str, str, str]:
        """Retrieves properties needed for m2m actions."""
        InstanceModel = instance.__class__  # pylint: disable=invalid-name
        # pylint: disable=invalid-name
        ThroughModel = getattr(getattr(InstanceModel, field_name), "through")

        field = InstanceModel._meta.get_field(field_name)
        related_field_name = field.related_query_name() if field.related_query_name else field.name

        if isinstance(field, models.ManyToManyField):
            # Forward relation
            from_field_name = field.m2m_field_name()
            to_field_name = field.m2m_reverse_field_name()
        elif isinstance(field, models.ManyToManyRel):
            field = field.remote_field
            from_field_name = field.m2m_reverse_field_name()
            to_field_name = field.m2m_field_name()
        else:
            # Reverse relation
            from_field_name = None
            to_field_name = None

            # Retrieve 'from' and 'to' fields automatically
            for _f in ThroughModel._meta.get_fields():
                if _f.is_relation:
                    if _f.name.startswith("from_"):
                        to_field_name = _f.name
                    elif _f.name.startswith("to_"):
                        from_field_name = _f.name
                    elif _f.related_model == InstanceModel:
                        to_field_name = _f.name
                    else:
                        from_field_name = _f.name

        return ThroughModel, field, related_field_name, from_field_name, to_field_name


class PermissionsMixin:
    """
    Defines common methods to check permissions on a object.
    """

    def _check_permissions(self, user, permission) -> bool:
        """
        Check if user has specif permission on the object.

        As default behavior, the check of the permission is sent to
        the manager itself. We assume all models inherit BaseManager
        and each manager should know how to check the permission by
        containing the method `check_object_permission`.
        """
        return self.__class__.objects.check_object_permission(self, user, permission)

    def can_read(self, user) -> bool:
        """
        Check if user has permissions to read the object.
        """
        return self._check_permissions(user, PERMISSIONS.READ)

    def can_write(self, user) -> bool:
        """
        Check if user has permissions to write on the object.
        """
        return self._check_permissions(user, PERMISSIONS.WRITE)

    def can_admin(self, user) -> bool:
        """
        Check if user has permissions to admin on the object.
        """
        return self._check_permissions(user, PERMISSIONS.ADMIN)

    def get_creator(self):
        """Returns object's creator"""
        # Prevent circular import | pylint: disable=import-outside-toplevel
        from app.core.users.models import User

        manager = self.__class__.objects
        path = getattr(manager, "_field", "created_by")

        # Get creator from the path
        obj = self
        for attr in path.split("__"):
            obj = getattr(obj, attr, None)
        return obj if isinstance(obj, User) else User.objects.get(pk=obj)


class SubModulesMixin:
    """
    Defines common methods to retrieve serializer and viewset.
    """

    @classmethod
    def get_viewset_class(cls) -> Type[ModelViewSet]:
        """
        Returns model serializer class
        """
        package = ".".join(cls.__module__.split(".")[:-1])
        module = importlib.import_module(package + ".views")
        return getattr(module, f"{cls.__name__}ViewSet")

    @classmethod
    def get_serializer_class(cls) -> Type[ModelSerializer]:
        """
        Returns model serializer class
        """
        package = ".".join(cls.__module__.split(".")[:-1])
        module = importlib.import_module(package + ".serializers")
        return getattr(module, f"{cls.__name__}Serializer")

    def get_serializer(self, **kwargs) -> ModelSerializer:
        """
        Returns a instance of the ModelSerializer with data and context.
        """
        serializer_class = self.__class__.get_serializer_class()

        # Making sure we have a context and a request in the serializer.
        # This is useful specially for background tasks, where the request doesn't exist
        kwargs["context"] = kwargs.get("context") or {}
        if "request" not in kwargs["context"]:
            kwargs["context"]["request"] = FakeRequest(user=get_current_user())
        return serializer_class(self, **kwargs)

    @classmethod
    def deserialize(cls, validate_data: bool = True, **kwargs):
        """
        Returns a instance of the Model with data provided from kwargs.
        Checks if fields exists and ads id for foreign keys.
        """
        serializer_class = cls.get_serializer_class()

        serializer = serializer_class(data=kwargs, fields_list=cls.WEBSOCKET_FIELDS_LIST)
        if validate_data:
            serializer.is_valid(raise_exception=True)
            data = serializer.validated_data
        else:
            data = serializer.data
        data.setdefault("id", kwargs.get("id"))
        return cls(**data)


class AppBaseModel(
    BulkActionsMixin,
    PermissionsMixin,
    SubModulesMixin,
    models.Model,
):
    """
    Defines common behavior that all models from DJ should have,
    without the tracking of who and when the instance was created and updated.
    """

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False, db_index=True)

    class Meta:
        abstract = True


class AppModel(AppBaseModel):
    """
    Defines common behavior that all models from DJ should have,
    including the tracking of who and when the instance was created and updated.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="%(app_label)s_%(class)s_created_by",
        null=True,
        blank=True,
        on_delete=models.SET(set_delete_user),
    )

    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="%(app_label)s_%(class)s_updated_by",
        null=True,
        blank=True,
        on_delete=models.SET(set_delete_user),
    )

    objects = SuperuserManager()

    class Meta:
        abstract = True
        ordering = ("-created_by",)

    @classmethod
    def classname(cls):
        """
        Return the name of the class as a string.
        """
        return str(cls.__name__)

    @classmethod
    def get_contenttype(cls):
        """
        Return contenttype id of the model.
        """
        if not hasattr(cls, "_contenttype"):
            cls._contenttype = ContentType.objects.get_for_model(cls).id
        return cls._contenttype

    @classmethod
    def get(cls, uuid: str | UUID):
        """
        Shortcut to return object by pk or None if it doesn't exist.
        """
        try:
            return cls.objects.get(pk=uuid)
        except ObjectDoesNotExist:
            return None

    @property
    def contenttype(self):
        """
        Return contenttype id of the model
        """
        return self.__class__.get_contenttype()

    def __str__(self):
        """
        Use UUID as string representation by default.
        """
        return str(self.pk)

    def __init__(self, *args, **kwargs) -> None:
        """
        Update tracked fields when object is initialized.
        """
        super().__init__(*args, **kwargs)
        self._update_tracked_fields()

    def save(self, *args, **kwargs) -> None:
        """
        Overrides default save method to execute pre and post save receivers.
        """
        created = getattr(self, "_is_new", not self.created_at)

        # Get list of all fields that has changed
        changed_fields = self._get_changed_fields() if not created else set()

        # Execute all pre_save receivers and save new kwargs
        # to be used in post save receivers
        pre_save_kwargs = {"created": created}
        for func in getattr(self, "pre_save_receivers", []):
            pre_save_kwargs.update(
                run_class_method(func, [self], changed_fields, **pre_save_kwargs) or {}
            )

        # Set the user that created/updated the object before saving on db
        user = get_current_user()
        if created:
            self.created_by = user
        self.updated_by = user
        super().save(*args, **kwargs)

        # Add old_values dict and execute all post_save receivers with it
        pre_save_kwargs.update({"old_values": {str(self.pk): self._old_values}})
        for func in getattr(self, "post_save_receivers", []):
            run_class_method(func, [self], changed_fields, **pre_save_kwargs)

        # Execute all post_save_background receivers in a celery task
        self.__class__.run_background_task(
            on_post_save_background, [self], changed_fields, **pre_save_kwargs
        )

        self._update_tracked_fields()

    def delete(self, *args, **kwargs):
        """
        Overrides default delete method to execute pre and post delete receivers.
        """

        # Execute all pre_delete receivers and save new kwargs
        # to be used in post save receivers
        pre_delete_kwargs = {}
        for func in getattr(self, "pre_delete_receivers", []):
            pre_delete_kwargs.update(run_class_method(func, [self], **pre_delete_kwargs) or {})

        # Replica of self needs to be created before deleting from database
        # because self it will be destroyed
        # NOTE: If WEBSOCKET_NOTIFICATIONS_ENABLED = False we don't enforce serializer.
        #       In this case we don't emit on_post_delete_background signal
        try:
            serialized_obj = self.get_serializer().data
        except AttributeError:
            serialized_obj = None

        obj = self.__class__.objects.get(pk=self.pk)
        ret = super().delete(*args, **kwargs)

        # Execute all post_delete receivers for this class
        post_delete_kwargs = {}
        for func in getattr(obj.__class__, "post_delete_receivers", []):
            post_delete_kwargs.update(run_class_method(func, [obj], **pre_delete_kwargs) or {})

        # Execute all post_save_background receivers in a celery task
        # NOTE: WEBSOCKET_NOTIFICATIONS_ENABLED=False might not have serializers
        if serialized_obj is not None:
            obj.__class__.run_background_task(
                on_post_delete_background, [serialized_obj], **post_delete_kwargs
            )

        return ret
