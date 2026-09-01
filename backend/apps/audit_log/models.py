from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_events",
    )
    action = models.CharField(max_length=100, db_index=True)
    object_type = models.CharField(max_length=100, db_index=True)
    object_id = models.CharField(max_length=255, blank=True)
    request_id = models.CharField(max_length=128, blank=True, db_index=True)
    payload = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [
            models.Index(fields=["actor", "created_at"], name="audit_actor_created_idx"),
            models.Index(fields=["object_type", "object_id"], name="audit_object_idx"),
        ]

    def __str__(self):
        return f"{self.action} {self.object_type}:{self.object_id or '-'}"
