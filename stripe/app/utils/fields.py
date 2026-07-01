import inspect
import json
import os
import random
import string

from secured_fields.fernet import get_fernet
from secured_fields.fields import EncryptedJSONField as _EncryptedJSONField

from django.core import checks
from django.core.validators import RegexValidator
from django.db import models

from app.utils.encoders import JSONEncoder

NAME_WITH_SPACES = r"^[\w\- ]+$"
NAME_WITHOUT_SPACES = r"^[\w\-]+$"


class AppFieldMixin:
    """
    This mixins adds extra args to the original Django fields,
    to add extra and specific behavior/settings for app.
    """

    track: bool = True

    def __init__(self, *args, track: bool = True, **kwargs) -> None:
        """
        Same as original Django models. Few settings where added.

        :param track: If true, this field will be check if has been
            changed during update. Defaults True.
        :type track: bool
        """
        kwargs.setdefault("blank", kwargs.get("null", False))
        super().__init__(*args, **kwargs)
        self.track = track


# -----------------------------------------------------------------------------
# Django default fields
# -----------------------------------------------------------------------------


class BooleanField(AppFieldMixin, models.BooleanField):
    """
    Same as original models.BooleanField. Only added specific DJ settings.
    """


class CharField(AppFieldMixin, models.CharField):
    """
    Same as original models.CharField. Only added specific DJ settings.
    """


class DateField(AppFieldMixin, models.DateField):
    """
    Same as original models.DateField. Only added specific DJ settings.
    """


class DateTimeField(AppFieldMixin, models.DateTimeField):
    """
    Same as original models.DateTimeField. Only added specific DJ settings.
    """


class EmailField(AppFieldMixin, models.EmailField):
    """
    Same as original models.EmailField. Only added specific DJ settings.
    """


class FloatField(AppFieldMixin, models.FloatField):
    """
    Same as original models.FloatField. Only added specific DJ settings.
    """


class ForeignKey(AppFieldMixin, models.ForeignKey):  # pylint: disable=abstract-method
    """
    Same as original models.ForeignKey. Only added specific DJ settings.
    """


class JSONField(AppFieldMixin, models.JSONField):
    """
    Same as original models.JSONField. Only added specific DJ settings.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("encoder", JSONEncoder)
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)


class EncryptedJSONField(AppFieldMixin, _EncryptedJSONField):
    """
    Same as secured_fields EncryptedJSONField but with the custom
    JSONEncoder that handles Decimal, UUID, etc.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("encoder", JSONEncoder)
        kwargs.setdefault("blank", True)
        super().__init__(*args, **kwargs)

    def get_db_prep_save(self, value, connection):
        """
        Encrypt and serialize the value before saving to the database.
        This overrides the default behavior to use our custom JSONEncoder and
        to ensure the value is encrypted before being saved.
        """
        if value is None:
            return None

        json_bytes = json.dumps(value, cls=self.encoder or JSONEncoder).encode()
        return get_fernet().encrypt(json_bytes).decode()


class OneToOneField(AppFieldMixin, models.OneToOneField):  # pylint: disable=abstract-method
    """
    Same as original models.OneToOneField. Only added specific DJ settings.
    """


class PositiveIntegerField(AppFieldMixin, models.PositiveIntegerField):
    """
    Same as original models.PositiveIntegerField. Only added specific DJ settings.
    """


class PositiveSmallIntegerField(AppFieldMixin, models.PositiveSmallIntegerField):
    """
    Same as original models.PositiveSmallIntegerField. Only added specific DJ settings.
    """


class TextField(AppFieldMixin, models.TextField):
    """
    Same as original models.TextField. Only added specific DJ settings.
    """


class TimeField(AppFieldMixin, models.TimeField):
    """
    Same as original models.TimeField. Only added specific DJ settings.
    """


class UUIDField(AppFieldMixin, models.UUIDField):
    """
    Same as original models.UUIDField. Only added specific DJ settings.
    """


# -----------------------------------------------------------------------------
# DJ image and file fields
# -----------------------------------------------------------------------------


def _upload_to(instance: object, filename: str) -> str:
    """
    Save media files with an hash instead of original names.
    """
    name, ext = os.path.splitext(filename)
    name = "".join(random.choice(string.ascii_lowercase + string.digits) for x in range(32))
    new_filename = f"{name}{ext.lower()}"
    fullpath = inspect.getfile(instance.__class__)
    path = f"{os.path.split(os.path.split(fullpath)[-2])[-1]}/{instance.__class__.__name__.lower()}"
    return os.path.join(path, new_filename)


class FileField(AppFieldMixin, models.FileField):
    """
    Same as original models.FileField. Only added specific DJ settings.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("upload_to", _upload_to)
        super().__init__(*args, **kwargs)


class ImageField(AppFieldMixin, models.ImageField):
    """
    Same as original models.ImageField. Only added specific DJ settings.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("upload_to", _upload_to)
        super().__init__(*args, **kwargs)


# -----------------------------------------------------------------------------
# DJ custom fields
# -----------------------------------------------------------------------------


class NameField(AppFieldMixin, models.CharField):
    """
    Same as original models.CharField. Only added specific DJ settings.
    """

    def __init__(self, *args, allow_spaces: bool = True, **kwargs):
        """
        Same as original Django CharField but with a default max_length=64.
        It was also added few more settings.

        :param track: If true, this field will be check if has been
            changed during update. Defaults True.
        :type track: bool
        :param allow_spaces: If true, the field can contain spaces
            besides r"[\\w\\-]". Defaults True.
        :type allow_spaces: bool
        """
        regex = NAME_WITH_SPACES if allow_spaces else NAME_WITHOUT_SPACES
        kwargs.setdefault("max_length", 64)
        kwargs.setdefault("validators", [RegexValidator(regex=regex)])
        super().__init__(*args, **kwargs)


class EnumField(AppFieldMixin, models.CharField):
    """
    Same as original models.CharField. Only added specific DJ settings.
    """

    def __init__(self, *args, enum=None, **kwargs):
        """
        Same as original Django CharField but with a default max_length=30.
        It was also added few more settings.

        :param enum: TextChoices class with the list of valid choices
        :type enum: type[TextChoices]
        :param track: If true, this field will be check if has
            been changed during update. Defaults True.
        :type track: bool
        :param allow_spaces: If true, the field can contain spaces
            besides [a-zA-Z_\\-]. Defaults True.
        :type allow_spaces: bool
        """

        # Making sure that we are receiving a valid TextChoices class
        if enum is not None:
            if hasattr(enum, "choices") and isinstance(enum, type):
                kwargs["choices"] = enum.choices
            else:
                kwargs["choices"] = "invalid"

        kwargs.setdefault("max_length", 15)
        super().__init__(*args, **kwargs)

    def _check_choices(self, *args, **kwargs):
        """
        In combination with __init__, checks if choices are declared and if they are invalid.
        """
        if not self.choices:
            return [
                checks.Error(
                    "EnumField must define an 'enum' attribute.",
                    obj=self,
                    id="fields.DJ2",
                )
            ]

        if self.choices == "invalid":
            return [
                checks.Error(
                    "EnumField 'enum' attribute must be a TextChoices class.",
                    obj=self,
                    id="fields.DJ2",
                )
            ]

        return super()._check_choices(*args, **kwargs)  # pylint: disable=no-member
