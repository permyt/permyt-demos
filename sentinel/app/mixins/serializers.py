from copy import deepcopy
from typing import Sequence, Any
from uuid import UUID

from rest_framework import serializers

from app.errors import ERRORS, raise_error
from app.utils.models import get_first_of

__all__ = ("AppModelSerializer",)


class AppModelSerializer(serializers.ModelSerializer):
    """
    AppModelSerializer which all serializers from DJ models must inherit.

    This contains automated behaviors such as:
    - Include time and user stamps by default
    - Include contenttype id of the model

    class Meta params:
        :param details_extra_fields: List of fields to be displayed only in details view
        :param select_related: List of foreign keys that should be fetch
            from db when using this serializer
        :param prefetch_related: List of lookups that should be prefetch
            from db when using this serializer
        :param read_permissions: List of foreign keys that user should have
            read permission to create or change the value
        :param write_permissions: List of foreign keys that user should have
            write permission to create or change the value
    """

    # Convert UUIDs to strings by default
    UUID_AS_STRING = False
    METADATA = True

    class Meta:
        model = None
        abstract = True

        # Fields viewset and others should prefetch for serialization performance
        select_related: Sequence[str] | None = None
        prefetch_related: Sequence[str] | None = None

        # List of fields to prevent new object creation,
        # unless they have permissions for the following fields
        read_permissions: Sequence[str] | None = None
        write_permissions: Sequence[str] | None = None

        # Extra fields to be used when serializer
        # is being used for detailed view of an object
        details_extra_fields: Sequence[str] | None = None
        details_extra_select_related: Sequence[str] | None = None
        details_extra_prefetch_related: Sequence[str] | None = None

        # List of fields that cannot be modified after object creation
        immutable_fields: Sequence[str] | None = None

    def __init__(
        self,
        *args,
        details: bool = False,
        fields_list: str = None,
        **kwargs,
    ):
        """
        Initialize specific data for ModelSerializer
        """
        self._view_details = details

        # Avoid modifying the original Meta class
        self.Meta = deepcopy(self.__class__.Meta)
        self.Meta.fields = get_first_of(self.Meta, fields_list, "fields")

        super().__init__(*args, **kwargs)

        # Ability to mark if fields permissions have been validated
        self._permissions_validated = False

        # Include user and timestamps by default
        self.fields["id"] = serializers.UUIDField(read_only=True)
        if self._should_add_metadata(*args, details=details, fields_list=fields_list, **kwargs):
            self.fields["contenttype"] = serializers.IntegerField(read_only=True)
            self.fields["created_by"] = serializers.UUIDField(
                read_only=True, source="created_by_id"
            )
            self.fields["created_at"] = serializers.DateTimeField(read_only=True)
            self.fields["updated_by"] = serializers.UUIDField(
                read_only=True, source="updated_by_id"
            )
            self.fields["updated_at"] = serializers.DateTimeField(read_only=True)

    def _should_add_metadata(self, *args, **kwargs) -> bool:
        """
        Check if fields_list should add metadata to the serializer
        """
        return self.METADATA

    def validate(self, attrs: Any) -> Any:
        """
        Validates attributes of the request.

        This method contains default checks when an object is being request to be created or
        updated from a request through an AppModelSerializer serializer. This method checks
        if user has the correct permissions based on `read_permissions` and `write_permissions`.

        NOTE: Permission checks should only be done if user is not None

        :param attrs: Attributes to be saved by the serializer
        :type attrs: Any
        :return: Attributes to be saved by the serializer
        :rtype: Any
        """

        request = self.context.get("request")
        user = request.user if request else None
        read_permissions = getattr(self.Meta, "read_permissions", None) or []
        write_permissions = getattr(self.Meta, "write_permissions", None) or []
        admin_permissions = getattr(self.Meta, "admin_permissions", None) or []
        func_by_index = {0: "can_read", 1: "can_write", 2: "can_admin"}

        # The following permissions checks are only needed if request is done by an user
        # and if read_permissions or write_permissions have declared fields
        if user and (read_permissions or write_permissions or admin_permissions):
            # The checks for read and write are the same, just the function is different.
            # The check should be done only if field is in attrs and it differs from previous value
            for i, permission in enumerate(
                [read_permissions, write_permissions, admin_permissions]
            ):
                for field in permission:
                    if field in attrs:
                        old_value = getattr(self.instance, field) if self.instance else None
                        new_value = attrs[field]

                        # Check if user has permission for the new value if it has changed
                        if (
                            (not self.instance or new_value != old_value)
                            and new_value is not None
                            and not getattr(new_value, func_by_index[i])(user)
                        ):
                            raise_error(ERRORS.PERMISSION_DENIED, field=field)

                        # Check if user has permission to remove from the old value
                        if (
                            (self.instance and new_value != old_value)
                            and old_value is not None
                            and not getattr(old_value, func_by_index[i])(user)
                        ):
                            raise_error(ERRORS.PERMISSION_DENIED, field=field)

        # Mark permissions as validated.
        # This is specially useful to check if validate have been overridden
        # without calling super().validate(attrs)
        self._permissions_validated = True

        # Check if immutable fields are being modified after creation
        if self.instance:
            for field in getattr(self.Meta, "immutable_fields", None) or []:
                if field in attrs and getattr(self.instance, field) != attrs[field]:
                    extra = "This field cannot be modified after creation."
                    raise_error(ERRORS.PERMISSION_DENIED, field=field, extra_message=extra)

        return attrs

    def to_representation(self, instance):
        """
        Convert instance to representation.
        If UUID_AS_STRING is True, convert UUIDs into strings.
        """
        attrs = super().to_representation(instance)
        if self.UUID_AS_STRING:
            for field in attrs:
                if isinstance(attrs[field], UUID):
                    attrs[field] = str(attrs[field])
        return attrs

    @classmethod
    def get_select_related(cls, details: bool = False):
        """Returns select related fields"""
        select_related = [*cls.get_meta_field("select_related", default=[])]  # copy list
        if details:
            select_related += cls.get_meta_field("details_extra_select_related", default=[])
        return select_related

    @classmethod
    def get_prefetch_related(cls, details: bool = False):
        """Returns prefetch related fields"""
        prefetch_related = [*cls.get_meta_field("prefetch_related", default=[])]  # copy list
        if details:
            prefetch_related += cls.get_meta_field("details_extra_prefetch_related", default=[])
        return prefetch_related

    @classmethod
    def get_meta_field(cls, field_name: str, default: Any = None):
        """
        Get a named attribute from Meta class. When a default argument is given,
        it is returned when the attribute doesn't exist.
        """
        return getattr(cls.Meta, field_name, None) or default

    def _get_meta_field(self, field_name: str, default: Any = None):
        """
        Get a named attribute from Meta class; When a default argument is given,
        it is returned when the attribute doesn't exist.
        """
        return self.__class__.get_meta_field(field_name, default=default)
