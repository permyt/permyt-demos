import importlib
import json

from functools import wraps
from typing import Callable

from django.apps import apps
from django.db.models import Model
from django.http import JsonResponse

ModelOrListOfModels = str | Model | list[Model | str]


# -----------------------------------------------------------------------------
# Pre & Post save decorators
# -----------------------------------------------------------------------------


class DecoratorReceivers:
    """Class to store decorator receivers to be run on after ready."""

    receivers = []

    @classmethod
    def setup(cls):
        """
        Setup all declared receivers, both for on_post_save and on_post_delete decorators.

        NOTE: This code is executed from MainAppConfig after all models being ready.
        This is to make sure we can declare circular dependencies.
        """

        # Sort receivers by priority before adding them to the list
        for receiver in sorted(cls.receivers, key=lambda r: r["priority"]):
            for mdl in receiver["models"]:
                _model = cls.get_model(receiver["func"], mdl) if isinstance(mdl, str) else mdl
                if not getattr(_model, receiver["receivers_name"]):
                    setattr(_model, receiver["receivers_name"], [])
                getattr(_model, receiver["receivers_name"]).append(receiver["model_path"])

    @classmethod
    def get_model(cls, func: callable, model_path: str) -> Model:
        """
        Return model based on its path.

        The model can be added as name only (inside where decorator was declared), relative
        app name or absolute path.

        :param func: Method that is wrapped by @on_post_save or @on_post_delete decorators
        :type func: Callable
        :param model_path: Model name, relative app path or absolute model path.
        :type model_path: str
        :return: Return real model that inherits Model
        :rtype: Model
        """
        split_model_path = model_path.split(".")
        path_size = len(split_model_path)

        # It means it was only passed model name and we should get it from same file
        if path_size == 1:
            module = importlib.import_module(func.__module__)
            return getattr(module, model_path)

        # It means it was passed a relative path of the model
        # and we should use django app to get the model
        if path_size == 2:
            return apps.get_model(model_path)

        # It means it was passed the full path of model, we should get by importlib
        module = importlib.import_module(".".join(split_model_path[:-1]))
        return getattr(module, split_model_path[-1])

    @classmethod
    def add(
        cls,
        func: Callable,
        model: ModelOrListOfModels,
        receivers_name: str,
        priority: int = None,
    ) -> Callable:
        """
        Adds method to the set of functions that must be executed
        when objects are created, updated or deleted for a specific model or models.

        :param func: Method that is wrapped by pre and post save/delete decorators
        :type func: Callable
        :param model: Model or list of models that should fire this method
        :type model: ModelOrListOfModels
        :param receivers_name: Type of receivers that func should be attached
        :type receivers_name: str
        :param priority: Priority of the task. Lower numbers runs first. Defaults to 100
        :type priority: int
        :return: func wrapped in a @classmethod decorator
        :rtype: Callable
        """
        model_path = f"{func.__module__}.{func.__qualname__}"
        model = model or func.__qualname__.split(".")[0]
        models = model if isinstance(model, (list, tuple)) else [model]
        cls.receivers.append(
            {
                "func": func,
                "models": models,
                "receivers_name": receivers_name,
                "model_path": model_path,
                "priority": priority or 100,
            }
        )
        return classmethod(func)


# -----------------------------------------------------------------------------
# Save: pre, post & background
# -----------------------------------------------------------------------------


def on_pre_save(model: ModelOrListOfModels | None = None, priority: int = 100) -> Callable:
    """
    Executes the attached classmethod before creating or updating objects.

    How to use it:
    ```
    class A:
        @on_pre_save()
        def execute_before_save(
            cls,
            objects: list[AppModel],
            fields: set[str],
            created: bool = False,
            **kwargs,
        ):
            '''
            The code of this function will be executed in the current thread
            before one or more objects from class A is about to be created or updated.
            '''

    class B:
        @on_pre_save(model=A, priority=50)
        def execute_before_save(
            cls,
            objects: list[AppModel],
            fields: set[str],
            created: bool = False,
            **kwargs,
        ):
            '''
            The code of this function will be executed in the current thread
            before one or more objects from class A is about to be created or updated.
            '''
    ```

    :param model: Model or list of models that should fire this method. Defaults to method class.
    :type model: ModelOrListOfModels
    :param priority: Priority of the task. Lower numbers runs first. Defaults to 100
    :type priority: int
    :return: classmethod function
    :rtype: Callable
    """

    def wrapper(func):
        return DecoratorReceivers.add(func, model, "pre_save_receivers", priority=priority)

    return wrapper


def on_post_save(model: ModelOrListOfModels | None = None, priority: int = 100) -> Callable:
    """
    Executes the attached classmethod when data has been created or updated
    in the current thread.

    How to use it:
    ```
    class A:
        @on_post_save()
        def execute_after_save(
            cls,
            objects: list[AppModel],
            fields: set[str],
            created: bool = False,
            **kwargs,
        ):
            '''
            The code of this function will be executed in the current thread
            when one or more objects from class A have been created or updated.
            '''

    class B:
        @on_post_save(model=A, priority=50)
        def execute_after_save(
            cls,
            objects: list[AppModel],
            fields: set[str],
            created: bool = False,
            **kwargs,
        ):
            '''
            The code of this function will be executed in the current thread
            when one or more objects from class A have been created or updated.
            '''
    ```

    :param model: Model or list of models that should fire this method. Defaults to method class.
    :type model: ModelOrListOfModels
    :param priority: Priority of the task. Lower numbers runs first. Defaults to 100
    :type priority: int
    :return: classmethod function
    :rtype: Callable
    """

    def wrapper(func):
        return DecoratorReceivers.add(func, model, "post_save_receivers", priority=priority)

    return wrapper


def on_post_save_background(
    model: ModelOrListOfModels | None = None, priority: int = 100
) -> Callable:
    """
    Executes the attached classmethod when data has been created or updated
    on a background task (celery).

    How to use it:
    ```
    class A:
        @on_post_save_background()
        def execute_after_save_on_bg(
            cls,
            objects: list[AppModel],
            fields: set[str],
            created: bool = False,
            **kwargs,
    ):
            '''
            The code of this function will be executed on a background task (celery)
            when one or more objects from class A have been created or updated.
            '''

    class B:
        @on_post_save_background(model=A, priority=50)
        def execute_after_save_on_bg(
            cls,
            objects: list[AppModel],
            fields: set[str],
            created: bool = False,
            **kwargs,
        ):
            '''
            The code of this function will be executed on a background task (celery)
            when one or more objects from class A have been created or updated.
            '''
    ```

    :param model: Model or list of models that should fire this method. Defaults to method class.
    :type model: ModelOrListOfModels
    :param priority: Priority of the task. Lower numbers runs first. Defaults to 100
    :type priority: int
    :return: classmethod function
    :rtype: Callable
    """

    def wrapper(func):
        return DecoratorReceivers.add(
            func, model, "post_save_background_receivers", priority=priority
        )

    return wrapper


# -----------------------------------------------------------------------------
# Delete: pre, post & background
# -----------------------------------------------------------------------------


def on_pre_delete(model: ModelOrListOfModels | None = None, priority: int = 100) -> Callable:
    """
    Executes the attached classmethod before deleting objects.

    How to use it:
    ```
    class A:
        @on_pre_delete()
        def execute_before_delete(cls, objects: list[AppModel], **kwargs):
            '''
            The code of this function will be executed in the current thread
            before one or more objects from class A is about to be deleted.
            '''

    class B:
        @on_pre_delete(model=A, priority=50)
        def execute_before_delete(cls, objects: list[AppModel], **kwargs):
            '''
            The code of this function will be executed in the current thread
            before one or more objects from class A is about to be deleted.
            '''
    ```

    :param model: Model or list of models that should fire this method. Defaults to method class.
    :type model: ModelOrListOfModels
    :param priority: Priority of the task. Lower numbers runs first. Defaults to 100
    :type priority: int
    :return: classmethod function
    :rtype: Callable
    """

    def wrapper(func):
        return DecoratorReceivers.add(func, model, "pre_delete_receivers", priority=priority)

    return wrapper


def on_post_delete(model: ModelOrListOfModels | None = None, priority: int = 100) -> Callable:
    """
    Executes the attached classmethod when data has been deleted
    in the current thread.

    How to use it:
    ```
    class A:
        @on_post_delete()
        def execute_after_delete(cls, objects: list[AppModel], *args, **kwargs):
            '''
            The code of this function will be executed in the current thread
            when one or more objects from class A have been deleted.
            '''

    class B:
        @on_post_delete(model=A, priority=50)
        def execute_after_delete(cls, objects: list[AppModel], *args, **kwargs):
            '''
            The code of this function will be executed in the current thread
            when one or more objects from class A have been deleted.
            '''
    ```

    :param model: Model or list of models that should fire this method. Defaults to method class.
    :type model: ModelOrListOfModels
    :param priority: Priority of the task. Lower numbers runs first. Defaults to 100
    :type priority: int
    :return: classmethod function
    :rtype: Callable
    """

    def wrapper(func):
        return DecoratorReceivers.add(func, model, "post_delete_receivers", priority=priority)

    return wrapper


def on_post_delete_background(
    model: ModelOrListOfModels | None = None, priority: int = 100
) -> Callable:
    """
    Executes the attached classmethod when data has been deleted
    in a background task (celery).

    How to use it:
    ```
    class A:
        @on_post_delete_background()
        def execute_after_delete_on_bg(cls, objects: list[AppModel], **kwargs):
            '''
            The code of this function will be executed on a background task (celery)
            when one or more objects from class A are deleted
            '''

    class B:
        @on_post_delete_background(model=A, priority=50)
        def execute_after_delete_on_bg(cls, objects: list[AppModel], **kwargs):
            '''
            The code of this function will be executed on a background task (celery)
            when one or more objects from class A are deleted also.
            '''
    ```

    :param model: Model or list of models that should fire this method. Defaults to method class.
    :type model: ModelOrListOfModels
    :param priority: Priority of the task. Lower numbers runs first. Defaults to 100
    :type priority: int
    :return: classmethod function
    :rtype: Callable
    """

    def wrapper(func):
        return DecoratorReceivers.add(
            func, model, "post_delete_background_receivers", priority=priority
        )

    return wrapper


# -----------------------------------------------------------------------------
# Decorators for views
# -----------------------------------------------------------------------------


def json_error_handler(view_func):
    """
    Decorator that ensures error responses are returned as JSON with a status_code field.

    If the response is already JSON, it injects the status_code into the existing payload.
    If the response is not JSON (e.g. HTML), it replaces it with a clean JSON response
    using the HTTP reason phrase as the error message.

    Can be applied to function-based views, class-based views and DRF ViewSets
    by decorating the dispatch method.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        response = view_func(request, *args, **kwargs)

        if response.status_code >= 400:
            try:
                data = json.loads(response.content)
                data["status_code"] = response.status_code
            except json.JSONDecodeError:
                data = {"error": response.reason_phrase, "status_code": response.status_code}

            return JsonResponse(data, status=response.status_code)

        return response

    return wrapper
