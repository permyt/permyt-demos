from django.contrib.admin import ModelAdmin, TabularInline

__all__ = [
    "AppModelAdmin",
    "AppTabularInline",
]


class AppModelAdmin(ModelAdmin):
    readonly_fields = ("created_at", "created_by", "updated_at", "updated_by")


class AppTabularInline(TabularInline):
    exclude = ("created_at", "created_by", "updated_at", "updated_by")
    extra = 0
