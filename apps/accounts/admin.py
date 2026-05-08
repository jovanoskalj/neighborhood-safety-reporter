from django.contrib import admin

from .models import AuditLog, UserProfile


@admin.action(description="Activate selected users")
def activate_users(modeladmin, request, queryset):
    queryset.update(is_active=True)


@admin.action(description="Deactivate selected users")
def deactivate_users(modeladmin, request, queryset):
    queryset.update(is_active=False)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "role", "sector", "phone")
    list_filter = ("role", "sector")
    search_fields = ("user__username", "user__email", "phone")


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ("timestamp", "user", "action", "target_model", "target_id")
    list_filter = ("target_model", "timestamp")
    search_fields = ("action", "target_model")


admin.site.add_action(activate_users)
admin.site.add_action(deactivate_users)
