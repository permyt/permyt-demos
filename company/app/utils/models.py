import importlib
import uuid

from typing import Any


def get_model_class(full_path: str):
    """
    Return model class based on full path.

    :param full_path: Full path of model. Example: app.core.example.models.Item
    :type full_path: str
    """
    path = full_path.split(".")
    module = importlib.import_module(".".join(path[:-1]))
    return getattr(module, path[-1])


def run_class_method(full_path: str, *args, **kwargs) -> None:
    """
    Run class method based on full path.

    :param full_path: Full path of method. Example: app.core.example.models.Item.method_name
    :type full_path: str
    """

    path = full_path.split(".")
    module = importlib.import_module(".".join(path[:-2]))
    cls = getattr(module, path[-2])
    method = getattr(cls, path[-1])
    return method(*args, **kwargs)


def get_first_of(obj: Any, *args, default=None):
    """
    Return the first value that exists in a list of properties.
    """

    for arg in args:
        if arg is None:
            continue

        value = obj.get(arg) if isinstance(obj, dict) else getattr(obj, arg, None)
        if value:
            return value
    return default


def is_uuid(value: str) -> bool:
    """
    Check if value is a valid UUID.
    """
    if isinstance(value, uuid.UUID):
        return True

    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False


def get_attribute(obj: Any, attr: str, default=None) -> Any:
    """
    Get the value of an attribute from an object or dictionary.

    :param obj: The object or dictionary to get the attribute from.
    :param attr: The name of the attribute to retrieve.
    :param default: The default value to return if the attribute does not exist.
    :return: The value of the attribute or the default value.
    """
    if isinstance(obj, dict):
        return obj.get(attr, default)
    return getattr(obj, attr, default)
