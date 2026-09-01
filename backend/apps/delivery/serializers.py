from rest_framework import serializers
from .models import DeliverySnapshot, ExportJob


class ImageryIdsSerializer(serializers.Serializer):
    imagery_ids = serializers.ListField(child=serializers.CharField(max_length=64), allow_empty=True, max_length=200)


class ExportCreateSerializer(serializers.Serializer):
    format = serializers.ChoiceField(choices=[x[0] for x in ExportJob.FORMATS])


class ExportJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ExportJob
        fields = ["id", "format", "status", "imagery_ids", "snapshot", "file_size", "error", "expires_at", "created_at", "started_at", "finished_at"]


class DeliverySnapshotSerializer(serializers.ModelSerializer):
    owner_username = serializers.CharField(source="owner.username", read_only=True)
    imagery_count = serializers.SerializerMethodField()

    class Meta:
        model = DeliverySnapshot
        fields = ["id", "name", "description", "status", "imagery_ids", "imagery_count", "manifest", "owner", "owner_username", "frozen_at", "created_at"]
        read_only_fields = ["id", "status", "imagery_ids", "imagery_count", "manifest", "owner", "owner_username", "frozen_at", "created_at"]

    def get_imagery_count(self, obj):
        return len(obj.imagery_ids or [])


class DeliverySnapshotCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    description = serializers.CharField(required=False, allow_blank=True)
