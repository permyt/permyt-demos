from contextlib import contextmanager
from types import SimpleNamespace

from django.conf import settings

from permyt.exceptions import PermytError

from app import managers, models
from app.core.users.models import User


class Log(models.AppModel):
    """
    Audit log of actions performed in the system.
    """

    DELETE_AFTER = 60 * 24 * 90  # 3 months (in minutes)

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=32)
    data = models.EncryptedJSONField(default=dict)
    success = models.BooleanField(default=True)
    permyt_request_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    objects = managers.OwnerManager(field="user")

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        status = "ok" if self.success else "fail"
        return f"[{self.user} | {self.created_at}] {self.action} ({status})"

    @classmethod
    def info(cls, action: str, *, data: dict, success: bool = True, user=None):
        """
        Helper method to create a log entry.
        Respects the LOG_ACTIVITY setting to disable logging if needed.
        """
        if not settings.LOG_ACTIVITY:
            return
        cls.objects.create(user=user, action=action, data=data, success=success)

    @classmethod
    def error(cls, action: str, *, data: dict, user=None):
        """
        Helper method to create a log entry for a failed action.
        """
        cls.info(action, data=data, success=False, user=user)

    @classmethod
    def upsert_request(
        cls,
        user,
        permyt_request_id: str,
        *,
        action: str,
        data: dict,
        success: bool = True,
    ):
        """
        Upsert a single Log row for a given (user, permyt_request_id).

        ``action`` and ``success`` are replaced on each call; ``data`` is
        **merged** into the existing payload so accumulating context
        (e.g. the original description captured on submission) survives
        later status-only updates.
        """
        if not settings.LOG_ACTIVITY:
            return None
        obj, created = cls.objects.get_or_create(
            user=user,
            permyt_request_id=permyt_request_id,
            defaults={"action": action, "data": data, "success": success},
        )
        if not created:
            obj.action = action
            obj.data = {**(obj.data or {}), **data}
            obj.success = success
            obj.save()
        return obj

    @classmethod
    @contextmanager
    def activity(cls, action: str, *, data: dict | None = None, user=None):
        """
        Context manager that logs ``Log.info`` on clean exit and ``Log.error``
        on exception (then re-raises).

        Yields a mutable ``SimpleNamespace(data, user)`` so callers can enrich
        ``ctx.data`` or set ``ctx.user`` once it's resolved inside the block.
        """
        ctx = SimpleNamespace(data=dict(data or {}), user=user)
        try:
            yield ctx
        except Exception as exc:
            error_data: dict = {"error": type(exc).__name__, "message": str(exc)}
            if isinstance(exc, PermytError):
                error_data["code"] = exc.code
                if exc.extra_info:
                    error_data["extra_info"] = exc.extra_info
                status_code = getattr(exc, "status_code", None)
                if status_code is not None:
                    error_data["status_code"] = status_code
            cls.error(
                action,
                data={**ctx.data, **error_data},
                user=ctx.user,
            )
            raise
        cls.info(action, data=ctx.data, user=ctx.user)
