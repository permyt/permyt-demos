from app import admin

from .models import Nonce, RequestToken


@admin.register(Nonce)
class NonceAdmin(admin.AppModelAdmin):
    list_display = ("value", "created_at")
    search_fields = ("value",)
    list_filter = ("created_at",)


@admin.register(RequestToken)
class RequestTokenAdmin(admin.AppModelAdmin):
    list_display = ("jti", "user", "used", "expires_at", "created_at")
    list_filter = ("used", "created_at")
    search_fields = ("jti",)
    raw_id_fields = ("user",)
