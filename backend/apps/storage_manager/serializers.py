from rest_framework import serializers

from .models import StorageEndpoint, StorageObject, StorageScanJob


class StorageEndpointSerializer(serializers.ModelSerializer):
    has_credential = serializers.SerializerMethodField()

    class Meta:
        model = StorageEndpoint
        fields = [
            "id", "name", "endpoint_type", "mode", "root_uri", "credential_ref", "has_credential",
            "read_only", "enabled", "scan_policy", "status", "status_message", "last_check_at",
            "last_scan_at", "created_by", "created_at", "updated_at",
        ]
        extra_kwargs = {"credential_ref": {"write_only": True, "required": False}}
        read_only_fields = [
            "id", "has_credential", "status", "status_message", "last_check_at", "last_scan_at",
            "created_by", "created_at", "updated_at",
        ]

    def get_has_credential(self, obj):
        return bool(obj.credential_ref)

    def validate_endpoint_type(self, value):
        if value not in {StorageEndpoint.TYPE_LOCAL, StorageEndpoint.TYPE_NAS}:
            raise serializers.ValidationError("当前版本仅支持 local_directory 和 nas_smb。")
        return value

    def validate_root_uri(self, value):
        from .backends import validate_local_root
        try:
            validate_local_root(value)
        except Exception as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value

    def validate_credential_ref(self, value):
        value = value.strip()
        if any(token in value.lower() for token in ["password=", "secret=", "access_key="]):
            raise serializers.ValidationError("这里只能保存凭据引用，不要提交明文凭据。")
        return value


class StorageObjectSerializer(serializers.ModelSerializer):
    endpoint_name = serializers.CharField(source="endpoint.name", read_only=True)

    class Meta:
        model = StorageObject
        fields = [
            "id", "endpoint", "endpoint_name", "object_key", "scene_stem", "scene_group_key", "scene_role",
            "size_bytes", "modified_at", "fingerprint", "checksum_sha256", "status", "missing_scan_count",
            "missing_confirmed", "first_seen_at", "last_seen_at", "last_verified_at", "last_seen_scan",
            "source_metadata",
        ]
        read_only_fields = fields


class StorageScanJobSerializer(serializers.ModelSerializer):
    endpoint_name = serializers.CharField(source="endpoint.name", read_only=True)

    class Meta:
        model = StorageScanJob
        fields = [
            "id", "endpoint", "endpoint_name", "mode", "prefix", "status", "checkpoint", "files_scanned",
            "scenes_found", "new_count", "changed_count", "missing_count", "unchanged_count", "error_message",
            "created_by", "started_at", "finished_at", "created_at",
        ]
        read_only_fields = fields


class StorageReferenceIngestionSerializer(serializers.Serializer):
    object_ids = serializers.ListField(child=serializers.UUIDField(), allow_empty=False, max_length=200)
    project_id = serializers.IntegerField(required=False, allow_null=True)
    visibility = serializers.ChoiceField(choices=["public", "private"], default="private")
