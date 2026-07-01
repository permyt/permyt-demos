from app import admin

from .models import LoginToken, NoteField, User, UserFieldValue


@admin.register(User)
class UserAdmin(admin.AppModelAdmin):
    list_display = ("email", "permyt_user_id", "is_account_manager", "created_at")
    search_fields = ("email",)
    list_filter = ("is_account_manager", "is_staff")


@admin.register(LoginToken)
class LoginTokenAdmin(admin.AppModelAdmin):
    list_display = ("short_token", "user", "logged_in", "created_at")
    list_filter = ("logged_in",)
    raw_id_fields = ("user", "session")

    @admin.display(description="Token")
    def short_token(self, obj):
        return obj.token[:32] + "…" if len(obj.token) > 32 else obj.token


@admin.register(NoteField)
class NoteFieldAdmin(admin.AppModelAdmin):
    list_display = ("slug", "name", "created_at")
    search_fields = ("slug", "name")


@admin.register(UserFieldValue)
class UserFieldValueAdmin(admin.AppModelAdmin):
    list_display = ("user", "field", "created_at")
    list_filter = ("field",)
    raw_id_fields = ("user", "field")
