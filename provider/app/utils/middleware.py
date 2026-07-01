from __future__ import annotations

import json
import logging

from threading import local
from typing import Callable
from uuid import UUID

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import connections
from django.http import JsonResponse
from django.utils import timezone

logger = logging.getLogger("console")
USER_ATTR_NAME = getattr(settings, "LOCAL_USER_ATTR_NAME", "_current_user_uuid")
_thread_locals = local()


class LogMiddleware:
    """
    Logs time and database touches when executing a request.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """Count number of db connections made and execution time."""

        started_at = timezone.now()
        started_count = sum(len(c.queries) for c in connections.all())

        response = self.get_response(request)

        ended_time = timezone.now() - started_at
        ended_count = sum(len(c.queries) for c in connections.all()) - started_count

        logger.debug(f"\nQueries: {ended_count} | Time: {ended_time}")
        return response


class ErrorHandlerMiddleware:
    """
    Logs the error when an exception is raised during the request execution.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        if response.status_code >= 400:
            try:
                data = json.loads(response.content)
                data["status_code"] = response.status_code
            except json.JSONDecodeError:
                data = {"error": response.reason_phrase, "status_code": response.status_code}

            return JsonResponse(data, status=response.status_code)

        return response


class ThreadLocalUserMiddleware:
    """
    Sets the request user as the user executing the local thread.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        """
        While executing the request, it sets the same user in the local thread.
        """

        user = getattr(request, "user", None)
        token_user = getattr(request, "_token_user", None)
        local_user = user if user.is_authenticated else (token_user or user)

        with SetCurrentUser(local_user):
            response = self.get_response(request)
        return response


class SetCurrentUser:
    """
    Allow to set the user in a local thread.

    This is specially useful when running background tasks in celery.
    It enables to pass the user that requested the execution of the task
    and set all data updates as `created_by` and `updated_by` by her.

    The correct way to use is:
    ```
    with SetCurrentUser(user):
        do_some_action_as_this_user
        ....
    ```
    """

    def __init__(
        self, user: AbstractUser | UUID | str | None, keep_prev_user_on_exit: bool = False
    ):
        """
        Initialize the with handler with a specific user.

        ```
        with SetCurrentUser(user):
            do_some_action_as_this_user
            ....
        ```

        :param user: User to be used during execution of the code.
        :type user: User|UUID|str | None
        :param keep_prev_user_on_exit: Add back the previous user when exiting
        :type keep_prev_user_on_exit: bool
        """
        # Preventing circular imports | pylint: disable=import-outside-toplevel
        from app.core.users.models import User

        if isinstance(user, User):
            self.user = user
        elif isinstance(user, (str, UUID)):
            self.user = User.objects.filter(pk=str(user)).last()
        else:
            self.user = None

        # Tests and background tasks use this handler to simulate a request for an user.
        # When background tasks are executed in tests, we need to prevent them to clear
        # the previous user and avoid side effects. For normal runs, we don't need to
        # keep the previous user unless is explicit requested.
        self._keep_prev_user_on_exit = keep_prev_user_on_exit
        if settings.TEST or keep_prev_user_on_exit:
            self._previous_user = get_current_user()

    def __enter__(self):
        """
        When entering the with handler, set the user for the local thread.
        """

        self._set_current_user(lambda _: self.user)
        return self.user

    def __exit__(self, *args, **kwargs):
        """
        Remove the user from local thread when exiting the with handler.
        """
        if settings.TEST or self._keep_prev_user_on_exit:
            # Check init method for more details
            self._set_current_user(lambda _: self._previous_user)
        else:
            self._set_current_user(lambda _: None)

    def _set_current_user(self, user_fun: Callable[..., AbstractUser]):
        """
        Sets  user on the local thread.
        """
        # pylint: disable=unnecessary-dunder-call
        setattr(_thread_locals, USER_ATTR_NAME, user_fun.__get__(user_fun, local))


def get_current_user() -> AbstractUser | None:
    """
    Helper to return current user being used in the local tread.

    :return: Current user in the local thread
    :rtype: User | None
    """
    current_user = getattr(_thread_locals, USER_ATTR_NAME, None)
    if callable(current_user):
        current_user = current_user()
    return current_user
