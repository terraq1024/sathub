from rest_framework import serializers

from .models import IngestionItem, IngestionJob


class UrlImportSerializer(serializers.Serializer):
    visibility = serializers.ChoiceField(choices=[("public", "Public"), ("private", "Private")], default="private")
    project_id = serializers.IntegerField(required=False, allow_null=True)
    urls = serializers.CharField()

    def validate_urls(self, value):
        urls = [line.strip() for line in value.splitlines() if line.strip()]
        if not urls:
            raise serializers.ValidationError("At least one URL is required.")
        return urls


class ZipUploadSerializer(serializers.Serializer):
    visibility = serializers.ChoiceField(choices=[("public", "Public"), ("private", "Private")], default="private")
    project_id = serializers.IntegerField(required=False, allow_null=True)
    file = serializers.FileField()

    def validate_file(self, value):
        if not value.name.lower().endswith((".zip", ".7z")):
            raise serializers.ValidationError("Only .zip and .7z files are supported.")
        return value


class ArchiveCheckSerializer(serializers.Serializer):
    filename = serializers.CharField()

    def validate_filename(self, value):
        filename = value.strip()
        if not filename.lower().endswith((".zip", ".7z")):
            raise serializers.ValidationError("Only .zip and .7z files are supported.")
        return filename


class FolderUploadSerializer(serializers.Serializer):
    visibility = serializers.ChoiceField(choices=[("public", "Public"), ("private", "Private")], default="private")
    project_id = serializers.IntegerField(required=False, allow_null=True)
    files = serializers.ListField(child=serializers.FileField(), allow_empty=False)
    relative_paths = serializers.ListField(child=serializers.CharField(), allow_empty=False)

    def validate(self, attrs):
        if len(attrs["files"]) != len(attrs["relative_paths"]):
            raise serializers.ValidationError("files and relative_paths must have the same length.")
        return attrs


class IngestionItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = IngestionItem
        fields = [
            "id",
            "job",
            "source",
            "source_kind",
            "status",
            "raw_path",
            "cog_path",
            "stac_id",
            "image_id",
            "scene_key",
            "duplicate_of",
            "metadata_status",
            "relative_path",
            "error_message",
            "retry_count",
            "created_at",
            "updated_at",
        ]


class IngestionJobSerializer(serializers.ModelSerializer):
    project_name = serializers.CharField(source="project.name", read_only=True)
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)

    class Meta:
        model = IngestionJob
        fields = [
            "id",
            "created_by",
            "created_by_username",
            "project",
            "project_name",
            "source_type",
            "status",
            "total_count",
            "success_count",
            "failed_count",
            "skipped_count",
            "warning_count",
            "source_payload",
            "error_message",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ]
