from app import admin

from .models import Nonce


@admin.register(Nonce)
class NonceAdmin(admin.AppModelAdmin):
    list_display = ("value", "created_at")
    search_fields = ("value",)
    list_filter = ("created_at",)
