from rest_framework import serializers

from apps.projects.models import Project
from apps.projects.services import user_can_access_project

from .models import ImageryDataset, ImageryDatasetMember, ImageryRecord, ImagerySavedSearch


class ImageryQuerySerializer(serializers.Serializer):
    project_id = serializers.CharField(required=False)
    platform = serializers.CharField(required=False)
    sensor_type = serializers.ChoiceField(required=False, choices=['sar', 'optical'])
    source_vendor = serializers.CharField(required=False)
    satellite_name = serializers.CharField(required=False)
    sensor = serializers.CharField(required=False)
    imaging_mode = serializers.CharField(required=False)
    product_level = serializers.CharField(required=False)
    polarization = serializers.CharField(required=False)
    metadata_status = serializers.CharField(required=False)
    preview_status = serializers.CharField(required=False)
    cog_status = serializers.ChoiceField(required=False, choices=ImageryRecord.COG_STATUS_CHOICES)
    administrative_unit_id = serializers.CharField(required=False)
    classification_id = serializers.CharField(required=False)
    tag_id = serializers.CharField(required=False)
    resolution_min = serializers.FloatField(required=False, min_value=0)
    resolution_max = serializers.FloatField(required=False, min_value=0)
    time_start = serializers.DateTimeField(required=False)
    time_end = serializers.DateTimeField(required=False)
    bbox = serializers.CharField(required=False)
    geometry = serializers.JSONField(required=False)
    spatial_relation = serializers.ChoiceField(required=False, choices=["intersects", "within", "contains"], default="intersects")
    q = serializers.CharField(required=False, allow_blank=True)
    include_archived = serializers.BooleanField(required=False, default=False)
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=200, default=50)

    def validate_bbox(self, value):
        parts = [part.strip() for part in value.split(",")]
        if len(parts) != 4:
            raise serializers.ValidationError("bbox must be min_lon,min_lat,max_lon,max_lat.")
        try:
            values = [float(part) for part in parts]
        except ValueError as exc:
            raise serializers.ValidationError("bbox values must be numeric.") from exc
        if values[0] > values[2] or values[1] > values[3]:
            raise serializers.ValidationError("bbox minimums cannot be greater than maximums.")
        return values

    def validate_geometry(self, value):
        from .spatial import validate_geometry
        return validate_geometry(value)

    def validate(self, attrs):
        if attrs.get("resolution_min") is not None and attrs.get("resolution_max") is not None and attrs["resolution_min"] > attrs["resolution_max"]:
            raise serializers.ValidationError("resolution_min cannot be greater than resolution_max.")
        if attrs.get("time_start") and attrs.get("time_end") and attrs["time_start"] > attrs["time_end"]:
            raise serializers.ValidationError("time_start cannot be later than time_end.")
        return attrs


def _validate_projects(project_ids, request):
    projects = list(Project.objects.filter(pk__in=project_ids))
    found = {project.pk for project in projects}
    missing = [str(project_id) for project_id in project_ids if project_id not in found]
    if missing:
        raise serializers.ValidationError(f"Unknown projects: {', '.join(missing)}")
    if request:
        forbidden = [str(project.pk) for project in projects if not user_can_access_project(request.user, project)]
        if forbidden:
            raise serializers.ValidationError(f"You cannot use projects: {', '.join(forbidden)}")
    return list(dict.fromkeys(project_ids))


class ImageryRecordSerializer(serializers.ModelSerializer):
    effective_display_name = serializers.CharField(read_only=True)
    first_uploaded_by_username = serializers.CharField(source="first_uploaded_by.username", read_only=True)
    archived_by_username = serializers.CharField(source="archived_by.username", read_only=True, allow_null=True)
    project_ids = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()

    class Meta:
        model = ImageryRecord
        fields = [
            "id", "scene_key", "source_name", "display_name", "effective_display_name", "description",
            "platform_code", "satellite_name", "sensor", "imaging_mode", "imaging_mode_detail",
            "polarization", "polarizations", "product_level", "acquisition_time", "acquisition_start",
            "acquisition_end", "resolution_m", "bbox", "geometry", "metadata_status", "spatial_status",
            "preview_status", "cog_status", "cog_path", "cog_error", "cog_updated_at", "status", "project_ids", "first_uploaded_by", "first_uploaded_by_username",
            "is_archived", "archived_at", "archived_by", "archived_by_username", "can_manage",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_project_ids(self, obj):
        return list(obj.project_tags.values_list("project_id", flat=True))

    def get_can_manage(self, obj):
        request = self.context.get("request")
        return obj.can_manage(request.user) if request else False


class ImageryUpdateSerializer(serializers.Serializer):
    display_name = serializers.CharField(required=False, allow_blank=True, max_length=512, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, trim_whitespace=True)
    project_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        required=False,
        allow_empty=True,
        max_length=200,
    )

    def validate_project_ids(self, value):
        return _validate_projects(value, self.context.get("request"))

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("At least one editable field is required.")
        return attrs


class ImageryBatchSerializer(serializers.Serializer):
    ACTION_ARCHIVE = "archive"
    ACTION_RESTORE = "restore"
    ACTION_ADD_PROJECT = "add_project"
    ACTION_REMOVE_PROJECT = "remove_project"

    action = serializers.ChoiceField(choices=[ACTION_ARCHIVE, ACTION_RESTORE, ACTION_ADD_PROJECT, ACTION_REMOVE_PROJECT])
    imagery_ids = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=False,
        max_length=200,
    )
    project_id = serializers.IntegerField(required=False, min_value=1)

    def validate_imagery_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("imagery_ids cannot contain duplicates.")
        return value

    def validate(self, attrs):
        project_actions = {self.ACTION_ADD_PROJECT, self.ACTION_REMOVE_PROJECT}
        if attrs["action"] in project_actions and "project_id" not in attrs:
            raise serializers.ValidationError({"project_id": "This field is required for project actions."})
        if attrs["action"] not in project_actions and "project_id" in attrs:
            raise serializers.ValidationError({"project_id": "This field is only valid for project actions."})
        if "project_id" in attrs:
            _validate_projects([attrs["project_id"]], self.context.get("request"))
        return attrs


class ImageryDatasetWriteSerializer(serializers.ModelSerializer):
    imagery_ids = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        allow_empty=True,
        max_length=200,
        write_only=True,
    )

    class Meta:
        model = ImageryDataset
        fields = ["name", "description", "membership_type", "query_definition", "refresh_mode", "imagery_ids"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("The dataset name cannot be blank.")
        return value

    def validate_imagery_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("imagery_ids cannot contain duplicates.")
        return value

    def validate(self, attrs):
        membership = attrs.get("membership_type", getattr(self.instance, "membership_type", ImageryDataset.MEMBERSHIP_STATIC))
        if membership == ImageryDataset.MEMBERSHIP_QUERY and not attrs.get("query_definition", getattr(self.instance, "query_definition", {})):
            raise serializers.ValidationError({"query_definition": "Query datasets require query_definition."})
        if membership == ImageryDataset.MEMBERSHIP_QUERY and attrs.get("imagery_ids"):
            raise serializers.ValidationError({"imagery_ids": "Query datasets are populated by refresh."})
        return attrs


class ImageryDatasetMemberSerializer(serializers.ModelSerializer):
    imagery_id = serializers.CharField(source="imagery.pk", read_only=True)
    source_name = serializers.CharField(source="imagery.source_name", read_only=True)
    display_name = serializers.CharField(source="imagery.display_name", read_only=True)
    effective_display_name = serializers.CharField(source="imagery.effective_display_name", read_only=True)
    acquisition_time = serializers.DateTimeField(source="imagery.acquisition_time", read_only=True)
    platform_code = serializers.CharField(source="imagery.platform_code", read_only=True)
    satellite_name = serializers.CharField(source="imagery.satellite_name", read_only=True)
    polarization = serializers.CharField(source="imagery.polarization", read_only=True)
    bbox = serializers.JSONField(source="imagery.bbox", read_only=True)
    is_archived = serializers.BooleanField(source="imagery.is_archived", read_only=True)
    thumbnail_url = serializers.SerializerMethodField()
    preview_url = serializers.SerializerMethodField()

    class Meta:
        model = ImageryDatasetMember
        fields = [
            "imagery_id", "source_name", "display_name", "effective_display_name", "acquisition_time",
            "platform_code", "satellite_name", "polarization", "bbox", "is_archived", "position", "enabled",
            "thumbnail_url", "preview_url", "added_by", "added_at",
        ]

    def _asset_url(self, obj, role):
        roles = {asset.role for asset in obj.imagery.assets.all()}
        if role not in roles:
            return None
        request = self.context.get("request")
        path = f"/api/imagery/{obj.imagery_id}/assets/{role}"
        return request.build_absolute_uri(path) if request else path

    def get_thumbnail_url(self, obj):
        return self._asset_url(obj, "thumbnail")

    def get_preview_url(self, obj):
        return self._asset_url(obj, "preview")


def _dataset_members(obj):
    return list(obj.members.all())


class ImageryDatasetSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    member_count = serializers.SerializerMethodField()
    enabled_member_count = serializers.SerializerMethodField()
    bbox = serializers.SerializerMethodField()
    acquisition_start = serializers.SerializerMethodField()
    acquisition_end = serializers.SerializerMethodField()
    can_manage = serializers.SerializerMethodField()

    class Meta:
        model = ImageryDataset
        fields = [
            "id", "name", "description", "status", "revision", "membership_type", "query_definition", "refresh_mode", "last_refreshed_at", "member_count", "enabled_member_count",
            "bbox", "acquisition_start", "acquisition_end", "created_by", "created_by_username", "can_manage",
            "archived_at", "created_at", "updated_at",
        ]

    def get_member_count(self, obj):
        return len(_dataset_members(obj))

    def get_enabled_member_count(self, obj):
        return sum(1 for member in _dataset_members(obj) if member.enabled)

    def get_bbox(self, obj):
        bboxes = [member.imagery.bbox for member in _dataset_members(obj) if member.enabled and member.imagery.bbox and len(member.imagery.bbox) == 4]
        if not bboxes:
            return None
        return [
            min(value[0] for value in bboxes),
            min(value[1] for value in bboxes),
            max(value[2] for value in bboxes),
            max(value[3] for value in bboxes),
        ]

    def _times(self, obj):
        return [member.imagery.acquisition_time for member in _dataset_members(obj) if member.enabled and member.imagery.acquisition_time]

    def get_acquisition_start(self, obj):
        values = self._times(obj)
        return min(values) if values else None

    def get_acquisition_end(self, obj):
        values = self._times(obj)
        return max(values) if values else None

    def get_can_manage(self, obj):
        request = self.context.get("request")
        return obj.can_manage(request.user) if request else False


class ImageryDatasetDetailSerializer(ImageryDatasetSerializer):
    members = ImageryDatasetMemberSerializer(many=True, read_only=True)

    class Meta(ImageryDatasetSerializer.Meta):
        fields = ImageryDatasetSerializer.Meta.fields + ["members"]


class ImagerySavedSearchSerializer(serializers.ModelSerializer):
    created_by_username = serializers.CharField(source="created_by.username", read_only=True)
    can_manage = serializers.SerializerMethodField()

    class Meta:
        model = ImagerySavedSearch
        fields = ["id", "name", "description", "query_definition", "created_by", "created_by_username", "can_manage", "created_at", "updated_at"]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def get_can_manage(self, obj):
        request = self.context.get("request")
        return obj.can_manage(request.user) if request else False

    def validate_query_definition(self, value):
        serializer = ImageryQuerySerializer(data=value)
        serializer.is_valid(raise_exception=True)
        return serializer.validated_data

    def validate_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("The saved search name cannot be blank.")
        return value.strip()


class DatasetMemberAddSerializer(serializers.Serializer):
    imagery_ids = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=False,
        max_length=200,
    )

    def validate_imagery_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("imagery_ids cannot contain duplicates.")
        return value


class DatasetMemberOrderSerializer(serializers.Serializer):
    imagery_ids = serializers.ListField(
        child=serializers.CharField(max_length=64),
        allow_empty=True,
        max_length=200,
    )
    enabled_imagery_ids = serializers.ListField(
        child=serializers.CharField(max_length=64),
        required=False,
        allow_empty=True,
        max_length=200,
    )

    def validate_imagery_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("imagery_ids cannot contain duplicates.")
        return value

    def validate_enabled_imagery_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("enabled_imagery_ids cannot contain duplicates.")
        return value


class DatasetMemberUpdateSerializer(serializers.Serializer):
    enabled = serializers.BooleanField(required=False)
    move = serializers.ChoiceField(choices=["top", "up", "down", "bottom"], required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("At least one of enabled or move is required.")
        return attrs
