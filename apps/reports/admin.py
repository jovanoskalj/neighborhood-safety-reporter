from django.contrib import admin
from django.utils import timezone
from .models import Report


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ["id", "citizen", "category", "status", "priority", "is_deleted", "created_at"]
    list_filter = ["is_deleted", "status", "category", "sector"]
    actions = ["soft_delete_reports", "restore_reports"]

    def get_queryset(self, request):
        return Report.all_objects.all()

    @admin.action(description="Soft delete selected reports")
    def soft_delete_reports(self, request, queryset):
        queryset.update(is_deleted=True, deleted_at=timezone.now())

    @admin.action(description="Restore selected reports")
    def restore_reports(self, request, queryset):
        queryset.update(is_deleted=False, deleted_at=None)