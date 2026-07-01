from app import admin

from .models import Log


@admin.register(Log)
class LogAdmin(admin.AppModelAdmin):
    list_display = ("user", "action", "success", "permyt_request_id", "created_at")
    list_filter = ("action", "success")
    search_fields = ("permyt_request_id",)
    raw_id_fields = ("user",)
