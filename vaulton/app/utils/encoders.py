import json
import logging

from typing import Any
from uuid import UUID

from rest_framework.utils.encoders import JSONEncoder as RestFrameworkJSONEncoder

from django.db.models import Model
from django_redis.serializers.json import JSONSerializer

logger = logging.getLogger("console")


class JSONEncoder(RestFrameworkJSONEncoder):
    """
    JSONEncoder subclass that knows how to encode instances, classes,
    date/time/timedelta, decimal types, generators and other basic python objects.
    """

    def default(self, obj: Any) -> Any:
        """
        Makes sure errors background tasks are executed even if data is not serializable.
        This usually happens when data is added to kwargs of on_pre_save or on_pre_delete
        """
        # prevents circular imports | pylint: disable=import-outside-toplevel
        from django.contrib.contenttypes.models import ContentType

        # Convert UUID in string
        if isinstance(obj, UUID):
            return str(obj)

        # Convert model type in pk
        if isinstance(obj, type(Model)):
            return ContentType.objects.get_for_model(obj).id

        # Convert model object in pk
        if isinstance(obj, Model):
            pk = obj.pk
            return pk if isinstance(pk, int) else str(pk)

        try:
            return super().default(obj)
        except Exception:  # Allows silent-errors | pylint: disable=broad-except
            return str(obj) if obj is not None else None

    @classmethod
    def dumps(cls, obj):
        """Method to be used as json.dumps for celery tasks"""
        return cls().encode(obj)

    @classmethod
    def loads(cls, obj):
        """Method to be used as json.loads for celery tasks"""
        return json.loads(obj)

    @classmethod
    def force_encoding(cls, obj):
        """
        Force obj to be encoded and decoded

        This is particularly useful during tests. Celery tasks runs inline and
        encode/decode is not executed unless we force it. This way, we can capture
        errors that might occur at that moment.
        """
        return json.loads(json.dumps(obj, cls=JSONEncoder))


class RedisSerializer(JSONSerializer):
    """
    This is used to serialize data for DjangoRedis cache.
    It is overriding the default JSONEncoder with the custom DJ encoder.
    """

    encoder_class = JSONEncoder


def log_formatted_json(data: Any, indent=2) -> None:
    """
    Log formatted json

    :param data: data to be logged
    :param indent: indent level
    """
    logger.info(json.dumps(data, indent=indent, cls=JSONEncoder))
