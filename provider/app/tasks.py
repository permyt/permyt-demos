import logging
import os
import subprocess
import traceback

from uuid import UUID

from celery import shared_task, states
from celery.app.task import Task as CeleryTask
from kombu.utils.uuid import uuid

from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.utils import timezone

from app.utils.encoders import JSONEncoder
from app.utils.middleware import SetCurrentUser
from app.utils.models import run_class_method

logger = logging.getLogger("console")


class RunTask:
    """
    Run task on background and save it's state.
    NOTE: Tasks will be run on foreground during tests or when it is forced.
    """

    _task = None
    _state = None
    _run_on_background = True

    def __init__(
        self,
        task,
        *args,
        run_on_background: bool = True,
        countdown: float = None,
        **kwargs,
    ):
        """
        :param task: Task to be executed
        :param *args: Task args
        :param **kwargs: Task kwargs
        :param run_on_background: True if task should run on background
        :param countdown: Number of seconds into the future that task
            should be executed. Defaults to immediate.
        """

        if settings.TEST or not run_on_background:
            # NOTE: Since tests runs background tasks inline,
            #       args and kwargs are not encode/decode.
            # The following code is to force encode/decode and avoid surprises in runtime.
            task(*JSONEncoder.force_encoding(args), **JSONEncoder.force_encoding(kwargs))
            self._run_on_background = False
            self._state = states.SUCCESS
        else:
            self._task = task.apply_async(args=args, kwargs=kwargs, countdown=countdown)

    @property
    def state(self) -> str:
        """Return task state."""
        if self._state is None and self._task:
            return self._task.state
        return self._state or states.STARTED


# No need to implement run | pylint: disable=abstract-method
class BaseTask(CeleryTask):
    """Task class to be used for celery tasks in app"""

    # The rest of arguments are passed in **options | pylint: disable=arguments-differ
    def apply_async(self, task_id=None, args=None, kwargs=None, **options):
        """Create BgTask and mark as RUNNING before apply_async"""
        task_id = task_id or uuid()
        return super().apply_async(task_id=task_id, args=args, kwargs=kwargs, **options)


# ---------------------------------------------------------------------------------
# Generic tasks for on_post_save_background and on_post_delete_background
# ---------------------------------------------------------------------------------


@shared_task(base=BaseTask, name="post_save_background")
def on_post_save_background(
    contenttype_id: int,
    object_ids: list[UUID | str],
    *args,
    task_user_id: str = None,
    **kwargs,
) -> None:
    """
    Execute on_post_save_background on async task for a specific model.

    It fetches objects from database and pass them to on_post_save_background method.

    :param contenttype_id: Content type of the objects that have been saved
    :type contenttype_id: int
    :param object_ids: Ids of objects that have been saved
    :type object_ids: list[UUID | str]
    :param task_user_id: User that saved the objects, defaults to None
    :type task_user_id: int, optional
    """
    with SetCurrentUser(task_user_id):
        model = ContentType.objects.get(id=contenttype_id).model_class()
        objects = model.objects.filter(pk__in=object_ids)

        # Execute all post_save_background receivers
        for func in getattr(model, "post_save_background_receivers", None) or []:
            run_class_method(func, objects, *args, **kwargs)

        # Notify users through websocket when channel is available
        model.notify_on_post_save(objects, *args, **kwargs)


@shared_task(base=BaseTask, name="post_delete_background")
def on_post_delete_background(
    contenttype_id: int,
    objects: list[dict],
    *args,
    task_user_id: str = None,
    **kwargs,
):
    """
    Execute on_post_delete_background on async task for a specific model.

    It creates temporary objects from the list of objects represented by dicts
    and pass them to on_post_delete_background method.

    :param contenttype_id: Content type of the objects that have been saved
    :type contenttype_id: int
    :param objects: List of objects as dict
    :type objects: list[Dict]
    :param task_user_id: User that saved the objects, defaults to None
    :type task_user_id: int, optional
    """

    with SetCurrentUser(task_user_id):
        content_type = ContentType.objects.get(id=contenttype_id)
        model = content_type.model_class()
        objects = [model.deserialize(**obj) for obj in objects]

        # Execute all post_delete_background receivers
        for func in getattr(model, "post_delete_background_receivers", None) or []:
            run_class_method(func, objects, *args, **kwargs)

        # Notify users through websocket when channel is available
        model.notify_on_post_delete(objects, *args, **kwargs)


@shared_task(base=BaseTask, name="run_class_method")
def run_class_method_on_background(
    contenttype_id: int,
    method_name: str,
    *args,
    self_obj: UUID = None,
    task_user_id: str = None,
    **kwargs,
):
    """
    Execute any class method on async task for a specific model.

    :param contenttype_id: Content type
    :type contenttype_id: int
    :param method_name: Method name to be executed
    :type method_name: str
    :param self_obj: Id of the object to be passed as self, defaults to None
    :type self_obj: UUID, optional
    :param task_user_id: User that triggered the method, defaults to None
    :type task_user_id: int, optional
    """
    with SetCurrentUser(task_user_id):
        content_type = ContentType.objects.get(id=contenttype_id)
        model = content_type.model_class()

        if self_obj:
            try:
                self_obj = model.objects.get(id=self_obj)
            except model.DoesNotExist:
                logger.error(f"Object with id {self_obj} does not exist for model {model}")
                return
            method = getattr(self_obj, method_name)
        else:
            method = getattr(model, method_name)
        method(*args, **kwargs)


# ---------------------------------------------------------------------------------
# Housekeeping tasks
# ---------------------------------------------------------------------------------

# hours * minutes * seconds
BACKUP_TIME_LIMIT = 3 * 60 * 60


@shared_task(
    name="backup_databases", time_limit=BACKUP_TIME_LIMIT, soft_time_limit=BACKUP_TIME_LIMIT
)
def backup_databases():
    """
    This task will backup all databases and send them to S3.
    Before it, it will rebuild the database indexes.
    """
    started_at = timezone.now()

    try:
        for conf in settings.DATABASES.values():
            # Create backup
            pwd = conf["PASSWORD"]
            name = conf["NAME"]
            user = conf["USER"]
            host = conf["HOST"] or "localhost"
            filename = f"/tmp/{name}.dump"
            subprocess.run(
                f"PGPASSWORD={pwd} pg_dump -d {name} -U {user} "
                f"-h {host} -Fc -Z 9 --file={filename}",
                check=False,
                shell=True,
            )

            # Send backup to S3
            hourly = started_at.strftime("%Y-%m-%dT%H:00")
            daily = started_at.date().isoformat()
            monthly = started_at.strftime("%Y-%m")
            targets = [
                f"s3://{settings.DB_BUCKET}/latest/{name}-latest.dump",
                f"s3://{settings.DB_BUCKET}/hourly/{name}-{hourly}.dump",
                f"s3://{settings.DB_BUCKET}/daily/{name}-{daily}.dump",
                f"s3://{settings.DB_BUCKET}/monthly/{name}-{monthly}.dump",
            ]
            for target in targets:
                subprocess.run(f"aws s3 cp {filename} {target}", check=False, shell=True)

            # Remove to prevent disk full
            os.remove(filename)
    except Exception as exc:  # pylint: disable=broad-except
        subject = "Error raised while backing-up databases"
        tb = traceback.format_exc()
        logger.error(f"{subject}: {exc}\n{tb}")
