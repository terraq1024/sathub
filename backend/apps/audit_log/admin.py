from django.contrib import admin

from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "actor", "action", "object_type", "object_id", "request_id", "ip")
    list_filter = ("action", "object_type", "created_at")
    search_fields = ("actor__username", "action", "object_type", "object_id", "request_id", "ip")
    readonly_fields = ("actor", "action", "object_type", "object_id", "request_id", "payload", "created_at", "ip")
    date_hierarchy = "created_at"
    ordering = ("-created_at", "-id")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return request.method in ("GET", "HEAD", "OPTIONS") and super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False
