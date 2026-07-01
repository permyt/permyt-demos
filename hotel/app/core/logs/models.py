from contextlib import contextmanager
from types import SimpleNamespace

from django.conf import settings

from permyt.exceptions import PermytError

from app import models
from app.core.bookings.models import Booking


class Log(models.AppModel):
    """
    Audit log of actions performed during a hotel booking flow.

    Logs are scoped per ``Booking`` (anonymous session). On a fresh demo run
    or session expiry, old logs are cascaded away with their booking.
    """

    DELETE_AFTER = 60 * 24 * 30  # 30 days (in minutes)

    booking = models.ForeignKey(
        Booking, null=True, blank=True, on_delete=models.SET_NULL, related_name="logs"
    )
    action = models.CharField(max_length=32)
    data = models.EncryptedJSONField(default=dict)
    success = models.BooleanField(default=True)
    permyt_request_id = models.CharField(max_length=64, null=True, blank=True, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self):
        status = "ok" if self.success else "fail"
        return f"[{self.booking_id} | {self.created_at}] {self.action} ({status})"

    @classmethod
    def info(cls, action: str, *, data: dict, success: bool = True, booking: Booking | None = None):
        if not settings.LOG_ACTIVITY:
            return
        cls.objects.create(booking=booking, action=action, data=data, success=success)

    @classmethod
    def error(cls, action: str, *, data: dict, booking: Booking | None = None):
        cls.info(action, data=data, success=False, booking=booking)

    @classmethod
    def upsert_request(
        cls,
        booking: Booking | None,
        permyt_request_id: str,
        *,
        action: str,
        data: dict,
        success: bool = True,
    ):
        """
        Upsert a single Log row for a given (booking, permyt_request_id).

        ``action`` and ``success`` are replaced on each call; ``data`` is
        **merged** so accumulating context (kind, description, …) survives
        later status-only updates.
        """
        if not settings.LOG_ACTIVITY:
            return None
        obj, created = cls.objects.get_or_create(
            booking=booking,
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
    def activity(cls, action: str, *, data: dict | None = None, booking: Booking | None = None):
        """
        Context manager that logs ``Log.info`` on clean exit and ``Log.error``
        on exception (then re-raises).
        """
        ctx = SimpleNamespace(data=dict(data or {}), booking=booking)
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
                booking=ctx.booking,
            )
            raise
        cls.info(action, data=ctx.data, booking=ctx.booking)
