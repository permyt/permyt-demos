from contextlib import contextmanager
from types import SimpleNamespace

from django.conf import settings

from permyt.exceptions import PermytError

from app import models
from app.core.verifications.models import Verification


class Log(models.AppModel):
    """
    Audit log of actions performed during an age-verification flow.

    Logs are scoped per ``Verification`` (anonymous session). On a fresh demo
    run or session expiry, old logs are cascaded away with their verification.
    """

    DELETE_AFTER = 60 * 24 * 30  # 30 days (in minutes)

    verification = models.ForeignKey(
        Verification, null=True, blank=True, on_delete=models.SET_NULL, related_name="logs"
    )
    action = models.CharField(max_length=32)
    data = models.EncryptedJSONField(default=dict)
    success = models.BooleanField(default=True)
    permyt_request_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        status = "ok" if self.success else "fail"
        return f"[{self.verification_id} | {self.created_at}] {self.action} ({status})"

    @classmethod
    def info(
        cls,
        action: str,
        *,
        data: dict,
        success: bool = True,
        verification: Verification | None = None,
    ):
        if not settings.LOG_ACTIVITY:
            return
        cls.objects.create(verification=verification, action=action, data=data, success=success)

    @classmethod
    def error(cls, action: str, *, data: dict, verification: Verification | None = None):
        cls.info(action, data=data, success=False, verification=verification)

    @classmethod
    def upsert_request(
        cls,
        verification: Verification | None,
        permyt_request_id: str,
        *,
        action: str,
        data: dict,
        success: bool = True,
    ):
        """
        Upsert a single Log row for a given (verification, permyt_request_id).

        ``action`` and ``success`` are replaced on each call; ``data`` is
        **merged** so accumulating context (kind, description, …) survives
        later status-only updates.
        """
        if not settings.LOG_ACTIVITY:
            return None
        obj, created = cls.objects.get_or_create(
            verification=verification,
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
    def activity(
        cls,
        action: str,
        *,
        data: dict | None = None,
        verification: Verification | None = None,
    ):
        """
        Context manager that logs ``Log.info`` on clean exit and ``Log.error``
        on exception (then re-raises).
        """
        ctx = SimpleNamespace(data=dict(data or {}), verification=verification)
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
                verification=ctx.verification,
            )
            raise
        cls.info(action, data=ctx.data, verification=ctx.verification)
