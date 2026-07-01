from rest_framework import serializers

from app.permissions import PERMISSIONS


class ListOfItemsField(serializers.ListField):
    """
    A field that accepts both a single item or a list of items.
    In case only an item is passed, it converts to list of items.
    """

    def to_internal_value(self, data):
        """Converts a single string to a list of strings."""
        if not isinstance(data, list):
            data = [data]
        return super().to_internal_value(data)


class ForeignKeyField(serializers.Field):
    """
    A field that accepts a foreign key value.
    It can be used to represent a foreign key relationship in serializers.
    """

    def __init__(self, **kwargs):
        self.model = kwargs.pop("model", None)
        self.permission = kwargs.pop("permission", PERMISSIONS.READ)
        self.pk_field = kwargs.pop("pk_field", "pk")
        self.allow_recursive = kwargs.pop("allow_recursive", True)
        super().__init__(**kwargs)

    def to_internal_value(self, data):
        try:
            return self.get_queryset().get(pk=data)
        except self.model.DoesNotExist:
            return self.fail("does_not_exist", pk_value=data)

    def get_queryset(self):
        request = self.context.get("request")
        user = request.user if request else None
        if not user:
            return self.model.objects.all()

        func = "as_reader" if self.permission == PERMISSIONS.READ else "as_writer"
        user = self.context.get("request").user
        return getattr(self.model.objects, func)(user)

    def to_representation(self, value):
        return getattr(value, self.pk_field)
