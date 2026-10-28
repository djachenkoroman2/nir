from django.contrib import admin

from .models import ActivityLog


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    """Журнал только для просмотра; удалять записи может лишь суперпользователь."""

    list_display = ['created_at', 'username', 'action', 'object_repr', 'path', 'ip']
    list_filter = ['action', 'created_at', 'user']
    search_fields = ['username', 'path', 'object_repr']
    date_hierarchy = 'created_at'
    list_select_related = ['user']

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
