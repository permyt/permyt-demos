from app import admin

from .models import Log


@admin.register(Log)
class LogAdmin(admin.AppModelAdmin):
    list_display = ("verification", "action", "success", "permyt_request_id", "created_at")
    search_fields = ("action", "permyt_request_id")
    list_filter = ("success", "action", "created_at")
    readonly_fields = ("data",)
    raw_id_fields = ("verification",)
