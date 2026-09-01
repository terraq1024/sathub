from rest_framework import serializers

from apps.imagery.models import ImageryRecord

from .exceptions import ProcessingError
from .models import ProcessingJob
from .raster_worker import (
    normalize_bbox,
    normalize_bands,
    validate_expression,
    validate_polygon,
)
from .services import source_path_for_imagery


class ProcessingJobSerializer(serializers.ModelSerializer):
    imagery_id = serializers.CharField(source="imagery.pk", read_only=True)
    imagery_name = serializers.CharField(
        source="imagery.effective_display_name",
        read_only=True,
    )
    created_by_username = serializers.CharField(
        source="created_by.username",
        read_only=True,
    )
    can_manage = serializers.SerializerMethodField()
    download_url = serializers.SerializerMethodField()

    class Meta:
        model = ProcessingJob
        fields = [
            "id",
            "imagery_id",
            "imagery_name",
            "created_by",
            "created_by_username",
            "status",
            "crop_geometry_type",
            "bbox",
            "geometry",
            "bands",
            "expression",
            "output_format",
            "output_media_type",
            "error_message",
            "attempts",
            "download_url",
            "can_manage",
            "started_at",
            "finished_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_can_manage(self, obj):
        request = self.context.get("request")
        return obj.can_manage(request.user) if request else False

    def get_download_url(self, obj):
        if obj.status != ProcessingJob.STATUS_SUCCEEDED or not obj.output_path:
            return None
        path = f"/api/processing/jobs/{obj.pk}/download"
        request = self.context.get("request")
        return request.build_absolute_uri(path) if request else path


class ProcessingJobWriteSerializer(serializers.ModelSerializer):
    imagery_id = serializers.PrimaryKeyRelatedField(
        queryset=ImageryRecord.objects.all(),
        source="imagery",
        required=False,
    )
    crop_geometry_type = serializers.ChoiceField(
        choices=ProcessingJob.CROP_CHOICES,
        required=False,
    )
    bbox = serializers.ListField(
        child=serializers.FloatField(),
        min_length=4,
        max_length=4,
        required=False,
        allow_null=True,
    )
    geometry = serializers.JSONField(required=False, allow_null=True)
    bands = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
        max_length=16,
    )
    expression = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500,
        trim_whitespace=True,
    )

    class Meta:
        model = ProcessingJob
        fields = [
            "imagery_id",
            "crop_geometry_type",
            "bbox",
            "geometry",
            "bands",
            "expression",
            "output_format",
        ]
        extra_kwargs = {"output_format": {"required": False}}

    def validate_bbox(self, value):
        if value is None:
            return None
        try:
            return normalize_bbox(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_geometry(self, value):
        if value is None:
            return None
        try:
            return validate_polygon(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_bands(self, value):
        try:
            return normalize_bands(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate_expression(self, value):
        try:
            validate_expression(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        return value.strip()

    def validate(self, attrs):
        instance = self.instance
        initial = self.initial_data

        imagery = attrs.get("imagery", instance.imagery if instance else None)
        if imagery is None:
            raise serializers.ValidationError({"imagery_id": "必须指定待处理影像"})
        if instance and "imagery" in attrs and attrs["imagery"].pk != instance.imagery_id:
            raise serializers.ValidationError({"imagery_id": "处理任务创建后不能更换影像"})
        if imagery.is_archived:
            raise serializers.ValidationError({"imagery_id": "已归档影像不能创建处理任务"})
        try:
            source_path_for_imagery(imagery)
        except ProcessingError as exc:
            raise serializers.ValidationError({"imagery_id": str(exc)}) from exc

        bbox_provided = "bbox" in initial and initial.get("bbox") is not None
        geometry_provided = "geometry" in initial and initial.get("geometry") is not None
        if bbox_provided and geometry_provided:
            raise serializers.ValidationError("bbox 和 geometry 只能提交一种")

        crop_type = attrs.get(
            "crop_geometry_type",
            instance.crop_geometry_type if instance else None,
        )
        if not crop_type:
            if bbox_provided:
                crop_type = ProcessingJob.CROP_BBOX
            elif geometry_provided:
                crop_type = ProcessingJob.CROP_POLYGON
            else:
                raise serializers.ValidationError("必须提交 bbox 或 Polygon geometry")
        elif "crop_geometry_type" not in attrs:
            if bbox_provided:
                crop_type = ProcessingJob.CROP_BBOX
            elif geometry_provided:
                crop_type = ProcessingJob.CROP_POLYGON

        bbox = attrs.get("bbox", instance.bbox if instance else None)
        geometry = attrs.get("geometry", instance.geometry if instance else None)
        if crop_type == ProcessingJob.CROP_BBOX:
            if not bbox_provided and instance and instance.crop_geometry_type != crop_type:
                bbox = None
            if bbox is None:
                raise serializers.ValidationError({"bbox": "bbox 裁剪必须提交 bbox"})
            attrs["bbox"] = bbox
            attrs["geometry"] = None
        else:
            if not geometry_provided and instance and instance.crop_geometry_type != crop_type:
                geometry = None
            if geometry is None:
                raise serializers.ValidationError({"geometry": "多边形裁剪必须提交 Polygon geometry"})
            attrs["bbox"] = None
            attrs["geometry"] = geometry
        attrs["crop_geometry_type"] = crop_type

        bands_explicit = "bands" in initial
        expression_explicit = "expression" in initial
        submitted_bands = attrs.get("bands", []) if bands_explicit else None
        submitted_expression = attrs.get("expression", "") if expression_explicit else None
        if submitted_bands and submitted_expression:
            raise serializers.ValidationError("bands 和 expression 不能同时使用")
        if expression_explicit and submitted_expression:
            attrs["bands"] = []
        elif bands_explicit and submitted_bands:
            attrs["expression"] = ""
        effective_bands = attrs.get("bands", instance.bands if instance else [])
        effective_expression = attrs.get(
            "expression",
            instance.expression if instance else "",
        )
        if effective_bands and effective_expression:
            raise serializers.ValidationError("bands 和 expression 不能同时使用")
        if not effective_bands and not effective_expression:
            raise serializers.ValidationError("bands 和 expression 至少需要填写一项")
        return attrs
