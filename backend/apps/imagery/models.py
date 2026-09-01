import uuid

from django.conf import settings
from django.db import models


class ImageryRecord(models.Model):
    STATUS_READY = "ready"
    STATUS_PARTIAL = "partial"
    STATUS_BROKEN = "broken"
    STATUS_CHOICES = [
        (STATUS_READY, "Ready"),
        (STATUS_PARTIAL, "Partial"),
        (STATUS_BROKEN, "Broken"),
    ]

    COG_NONE = "none"
    COG_QUEUED = "queued"
    COG_PROCESSING = "processing"
    COG_READY = "ready"
    COG_FAILED = "failed"
    COG_STALE = "stale"
    COG_STATUS_CHOICES = [
        (COG_NONE, "Not generated"),
        (COG_QUEUED, "Queued"),
        (COG_PROCESSING, "Processing"),
        (COG_READY, "Ready"),
        (COG_FAILED, "Failed"),
        (COG_STALE, "Stale"),
    ]

    id = models.CharField(max_length=64, primary_key=True)
    scene_key = models.CharField(max_length=255, unique=True)
    identity_hash = models.CharField(max_length=64, unique=True)
    stac_id = models.CharField(max_length=255, unique=True)
    source_name = models.CharField(max_length=512)
    display_name = models.CharField(max_length=512, blank=True)
    description = models.TextField(blank=True)
    archive_filename = models.CharField(max_length=512, null=True, blank=True, db_index=True)
    archive_job_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    platform_code = models.CharField(max_length=80, blank=True)
    satellite_name = models.CharField(max_length=255, blank=True)
    sensor = models.CharField(max_length=120, blank=True)
    imaging_mode = models.CharField(max_length=120, blank=True)
    imaging_mode_detail = models.CharField(max_length=120, blank=True)
    polarization = models.CharField(max_length=40, blank=True)
    polarizations = models.JSONField(default=list, blank=True)
    product_level = models.CharField(max_length=40, blank=True)
    acquisition_time = models.DateTimeField(null=True, blank=True, db_index=True)
    acquisition_start = models.DateTimeField(null=True, blank=True)
    acquisition_end = models.DateTimeField(null=True, blank=True)
    time_assumption = models.CharField(max_length=80, blank=True)
    orbit_id = models.CharField(max_length=80, blank=True)
    orbit_direction = models.CharField(max_length=40, blank=True)
    look_side = models.CharField(max_length=40, blank=True)
    resolution_m = models.FloatField(null=True, blank=True)
    pixel_spacing_range_m = models.FloatField(null=True, blank=True)
    pixel_spacing_azimuth_m = models.FloatField(null=True, blank=True)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    incidence_angle_near_deg = models.FloatField(null=True, blank=True)
    incidence_angle_far_deg = models.FloatField(null=True, blank=True)
    geometry = models.JSONField(null=True, blank=True)
    bbox = models.JSONField(null=True, blank=True)
    epsg = models.IntegerField(null=True, blank=True)
    metadata_status = models.CharField(max_length=30, default="partial")
    spatial_status = models.CharField(max_length=30, default="partial")
    preview_status = models.CharField(max_length=30, default="missing")
    cog_status = models.CharField(max_length=20, choices=COG_STATUS_CHOICES, default=COG_NONE, db_index=True)
    cog_path = models.TextField(blank=True)
    cog_error = models.TextField(blank=True)
    cog_updated_at = models.DateTimeField(null=True, blank=True)
    metadata_sources = models.JSONField(default=list, blank=True)
    raw_metadata = models.JSONField(default=dict, blank=True)
    stac_path = models.TextField(blank=True)
    first_uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="first_uploaded_imagery",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PARTIAL)
    is_archived = models.BooleanField(default=False, db_index=True)
    archived_at = models.DateTimeField(null=True, blank=True)
    archived_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="archived_imagery",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-acquisition_time", "-created_at"]
        indexes = [
            models.Index(fields=["platform_code", "imaging_mode"]),
            models.Index(fields=["polarization", "product_level"]),
            models.Index(fields=["metadata_status", "preview_status"]),
            models.Index(fields=["cog_status", "is_archived"]),
        ]

    def __str__(self):
        return self.scene_key

    @property
    def effective_display_name(self):
        return self.display_name or self.source_name

    def can_manage(self, user):
        return bool(user and user.is_authenticated and (user.is_staff or user.pk == self.first_uploaded_by_id))


class ImageryAsset(models.Model):
    ROLE_DATA = "data"
    ROLE_PREVIEW = "preview"
    ROLE_THUMBNAIL = "thumbnail"
    ROLE_METADATA = "metadata"
    ROLE_INCIDENCE = "incidence"
    ROLE_LOG = "log"
    ROLE_CHOICES = [
        (ROLE_DATA, "Data"),
        (ROLE_PREVIEW, "Preview"),
        (ROLE_THUMBNAIL, "Thumbnail"),
        (ROLE_METADATA, "Metadata"),
        (ROLE_INCIDENCE, "Incidence"),
        (ROLE_LOG, "Log"),
    ]
    ACCESS_REFERENCE = "reference"
    ACCESS_MANAGED = "managed"
    ACCESS_DERIVED = "derived"
    ACCESS_CHOICES = [
        (ACCESS_REFERENCE, "Reference"),
        (ACCESS_MANAGED, "Managed"),
        (ACCESS_DERIVED, "Derived"),
    ]

    imagery = models.ForeignKey(ImageryRecord, on_delete=models.CASCADE, related_name="assets")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    name = models.CharField(max_length=512)
    path = models.TextField()
    storage_object = models.ForeignKey(
        "storage_manager.StorageObject",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="imagery_assets",
    )
    access_mode = models.CharField(max_length=20, choices=ACCESS_CHOICES, default=ACCESS_MANAGED)
    media_type = models.CharField(max_length=120, blank=True)
    size_bytes = models.BigIntegerField(null=True, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["imagery", "role"], name="unique_imagery_asset_role"),
        ]


class ImageryProjectTag(models.Model):
    imagery = models.ForeignKey(ImageryRecord, on_delete=models.CASCADE, related_name="project_tags")
    project = models.ForeignKey("projects.Project", on_delete=models.CASCADE, related_name="imagery_tags")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["imagery", "project"], name="unique_imagery_project_tag"),
        ]


class ImageryDataset(models.Model):
    MEMBERSHIP_STATIC = "static"
    MEMBERSHIP_QUERY = "query"
    MEMBERSHIP_CHOICES = [(MEMBERSHIP_STATIC, "Static"), (MEMBERSHIP_QUERY, "Query")]
    REFRESH_MANUAL = "manual"
    REFRESH_ON_INGESTION = "on_ingestion"
    REFRESH_CHOICES = [(REFRESH_MANUAL, "Manual"), (REFRESH_ON_INGESTION, "On ingestion")]
    STATUS_ACTIVE = "active"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [
        (STATUS_ACTIVE, "Active"),
        (STATUS_ARCHIVED, "Archived"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    membership_type = models.CharField(max_length=20, choices=MEMBERSHIP_CHOICES, default=MEMBERSHIP_STATIC)
    query_definition = models.JSONField(default=dict, blank=True)
    refresh_mode = models.CharField(max_length=20, choices=REFRESH_CHOICES, default=REFRESH_MANUAL)
    last_refreshed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE, db_index=True)
    revision = models.PositiveIntegerField(default=1)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="imagery_datasets",
    )
    archived_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]

    def __str__(self):
        return self.name

    def can_manage(self, user):
        return bool(user and user.is_authenticated and (user.is_staff or user.pk == self.created_by_id))


class ImagerySavedSearch(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    query_definition = models.JSONField(default=dict)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="imagery_saved_searches")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at", "-created_at"]

    def can_manage(self, user):
        return bool(user and user.is_authenticated and (user.is_staff or user.pk == self.created_by_id))


class ImageryDatasetMember(models.Model):
    dataset = models.ForeignKey(ImageryDataset, on_delete=models.CASCADE, related_name="members")
    imagery = models.ForeignKey(ImageryRecord, on_delete=models.PROTECT, related_name="dataset_memberships")
    position = models.PositiveIntegerField(default=0)
    enabled = models.BooleanField(default=True)
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="added_imagery_dataset_members",
    )
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["position", "id"]
        constraints = [
            models.UniqueConstraint(fields=["dataset", "imagery"], name="unique_dataset_imagery"),
        ]
        indexes = [models.Index(fields=["dataset", "position"])]

    def __str__(self):
        return f"{self.dataset_id}:{self.imagery_id}"
