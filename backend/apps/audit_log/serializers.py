from rest_framework import serializers

from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEvent
        fields = [
            "id",
            "actor",
            "action",
            "object_type",
            "object_id",
            "request_id",
            "payload",
            "created_at",
            "ip",
        ]
        read_only_fields = fields
