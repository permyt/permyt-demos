from app import admin

from .models import LoginToken, User


@admin.register(User)
class UserAdmin(admin.AppModelAdmin):
    list_display = (
        "email",
        "full_name",
        "country",
        "permyt_user_id",
        "is_account_manager",
        "created_at",
    )
    search_fields = ("email", "full_name", "vat", "tax_id")
    list_filter = ("country", "is_account_manager", "is_staff")


@admin.register(LoginToken)
class LoginTokenAdmin(admin.AppModelAdmin):
    list_display = ("short_token", "user", "logged_in", "created_at")
    list_filter = ("logged_in",)
    raw_id_fields = ("user", "session")

    @admin.display(description="Token")
    def short_token(self, obj):
        return obj.token[:32] + "…" if len(obj.token) > 32 else obj.token
