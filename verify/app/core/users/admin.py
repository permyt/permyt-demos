from app import admin

from .models import User


@admin.register(User)
class UserAdmin(admin.AppModelAdmin):
    list_display = ("email", "created_at")
    search_fields = ("email",)
