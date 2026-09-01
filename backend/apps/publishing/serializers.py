from django.conf import settings
from rest_framework import serializers

from apps.imagery.models import ImageryDataset, ImageryRecord

from .models import ImageryService, ImageryServiceAsset, ServicePublishJob
from .services import service_zoom_range


class ServicePublishJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServicePublishJob
        fields = [
            "id", "status", "current_step", "progress", "error_message",
            "source_snapshot", "target_revision", "started_at", "finished_at",
            "created_at", "updated_at",
        ]


class ImageryServiceSerializer(serializers.ModelSerializer):
    source_type = serializers.CharField(source="service_type", read_only=True)
    imagery_id = serializers.SerializerMethodField()
    imagery_name = serializers.SerializerMethodField()
    dataset_id = serializers.SerializerMethodField()
    dataset_name = serializers.SerializerMethodField()
    imagery_count = serializers.SerializerMethodField()
    needs_update = serializers.SerializerMethodField()
    current_job = serializers.SerializerMethodField()
    last_error = serializers.SerializerMethodField()
    latest_job = serializers.SerializerMethodField()
    tilejson_url = serializers.SerializerMethodField()
    xyz_url = serializers.SerializerMethodField()
    ogcapi_url = serializers.SerializerMethodField()
    bbox = serializers.SerializerMethodField()
    minzoom = serializers.SerializerMethodField()
    maxzoom = serializers.SerializerMethodField()

    class Meta:
        model = ImageryService
        fields = [
            "id", "name", "service_key", "service_type", "source_type", "visibility",
            "status", "render_config", "error_message", "imagery_id", "imagery_name",
            "dataset_id", "dataset_name", "imagery_count", "needs_update", "current_job",
            "source_revision", "last_error", "latest_job", "tilejson_url", "xyz_url", "ogcapi_url",
            "bbox", "minzoom", "maxzoom",
            "published_at", "unpublished_at", "created_at", "updated_at",
        ]

    def _asset(self, obj):
        assets = list(obj.service_assets.all())
        return assets[0] if assets else None

    def get_imagery_id(self, obj):
        if obj.service_type == ImageryService.TYPE_DATASET_MOSAIC:
            return None
        asset = self._asset(obj)
        return asset.imagery_id if asset else None

    def get_imagery_name(self, obj):
        if obj.service_type == ImageryService.TYPE_DATASET_MOSAIC:
            return None
        asset = self._asset(obj)
        return asset.imagery.source_name if asset else None

    def get_dataset_id(self, obj):
        return str(obj.source_dataset_id) if obj.source_dataset_id else None

    def get_dataset_name(self, obj):
        return obj.source_dataset.name if obj.source_dataset_id else None

    def _source_assets(self, obj):
        assets = list(obj.service_assets.all())
        if assets or not obj.source_dataset_id:
            return assets
        return [
            member
            for member in obj.source_dataset.members.all()
            if member.enabled
        ]

    def get_imagery_count(self, obj):
        return len(self._source_assets(obj))

    def get_needs_update(self, obj):
        if not obj.source_dataset_id:
            return False
        return obj.source_revision != obj.source_dataset.revision

    def get_current_job(self, obj):
        job = next(
            (
                item for item in obj.publish_jobs.all()
                if item.status in [ServicePublishJob.STATUS_PENDING, ServicePublishJob.STATUS_RUNNING]
            ),
            None,
        )
        return ServicePublishJobSerializer(job).data if job else None

    def get_last_error(self, obj):
        if obj.error_message:
            return obj.error_message
        failed_job = next(
            (item for item in obj.publish_jobs.all() if item.status == ServicePublishJob.STATUS_FAILED),
            None,
        )
        return failed_job.error_message if failed_job else ""

    def get_latest_job(self, obj):
        jobs = list(obj.publish_jobs.all())
        return ServicePublishJobSerializer(jobs[0]).data if jobs else None

    def get_tilejson_url(self, obj):
        return self._public_service_url(obj, "tilejson")

    def get_xyz_url(self, obj):
        return self._public_service_url(obj, "tiles/{z}/{x}/{y}.png")

    def get_ogcapi_url(self, obj):
        return self._public_service_url(obj, "ogcapi")

    def _public_service_url(self, obj, suffix):
        base_url = getattr(settings, "PUBLIC_SERVICE_BASE_URL", "").rstrip("/")
        if not base_url:
            request = self.context.get("request")
            base_url = request.build_absolute_uri("/").rstrip("/") if request else ""
        return f"{base_url}/api/services/{obj.service_key}/{suffix}"

    def get_bbox(self, obj):
        bboxes = []
        for source in self._source_assets(obj):
            imagery = source.imagery
            if imagery.bbox and len(imagery.bbox) == 4:
                bboxes.append(imagery.bbox)
        if not bboxes:
            return None
        return [
            min(value[0] for value in bboxes),
            min(value[1] for value in bboxes),
            max(value[2] for value in bboxes),
            max(value[3] for value in bboxes),
        ]

    def _zoom_range(self, obj):
        if not hasattr(obj, "_serialized_zoom_range"):
            obj._serialized_zoom_range = service_zoom_range(obj)
        return obj._serialized_zoom_range

    def get_minzoom(self, obj):
        return self._zoom_range(obj)[0]

    def get_maxzoom(self, obj):
        return self._zoom_range(obj)[1]


class ImageryServiceCreateSerializer(serializers.Serializer):
    imagery_id = serializers.PrimaryKeyRelatedField(
        queryset=ImageryRecord.objects.all(), source="imagery", required=False,
    )
    dataset_id = serializers.PrimaryKeyRelatedField(
        queryset=ImageryDataset.objects.all(), source="dataset", required=False,
    )
    name = serializers.CharField(required=False, allow_blank=True, max_length=255)
    visibility = serializers.ChoiceField(choices=[ImageryService.VISIBILITY_AUTHENTICATED, ImageryService.VISIBILITY_PUBLIC], default=ImageryService.VISIBILITY_AUTHENTICATED)
    render_config = serializers.JSONField(required=False, default=dict)

    def validate(self, attrs):
        if ("imagery" in attrs) == ("dataset" in attrs):
            raise serializers.ValidationError("Exactly one of imagery_id or dataset_id is required.")
        dataset = attrs.get("dataset")
        if dataset and dataset.status != ImageryDataset.STATUS_ACTIVE:
            raise serializers.ValidationError({"dataset_id": "Archived datasets cannot be published."})
        imagery = attrs.get("imagery")
        if imagery and imagery.is_archived:
            raise serializers.ValidationError({"imagery_id": "Archived imagery cannot be published."})
        return attrs

    def validate_render_config(self, value):
        allowed = {"rescale", "colormap_name", "bidx", "expression"}
        unknown = set(value) - allowed
        if unknown:
            raise serializers.ValidationError(f"Unsupported render options: {', '.join(sorted(unknown))}")
        return value


class ImageryServiceUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ImageryService
        fields = ["name", "visibility", "render_config"]

    def validate_render_config(self, value):
        allowed = {"rescale", "colormap_name", "bidx", "expression"}
        unknown = set(value) - allowed
        if unknown:
            raise serializers.ValidationError(f"Unsupported render options: {', '.join(sorted(unknown))}")
        return value
