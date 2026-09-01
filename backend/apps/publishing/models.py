import uuid

from django.conf import settings
from django.db import models


class ImageryService(models.Model):
    TYPE_SINGLE_SCENE = "single_scene"
    TYPE_DATASET_MOSAIC = "dataset_mosaic"
    VISIBILITY_AUTHENTICATED = "authenticated"
    VISIBILITY_PUBLIC = "public"

    STATUS_DRAFT = "draft"
    STATUS_VALIDATING = "validating"
    STATUS_PREPARING = "preparing"
    STATUS_PUBLISHING = "publishing"
    STATUS_ONLINE = "online"
    STATUS_DEGRADED = "degraded"
    STATUS_OFFLINE = "offline"
    STATUS_FAILED = "failed"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [(value, value.replace("_", " ").title()) for value in [
        STATUS_DRAFT, STATUS_VALIDATING, STATUS_PREPARING, STATUS_PUBLISHING,
        STATUS_ONLINE, STATUS_DEGRADED, STATUS_OFFLINE, STATUS_FAILED, STATUS_ARCHIVED,
    ]]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    service_key = models.SlugField(max_length=80, unique=True)
    service_type = models.CharField(max_length=30, default=TYPE_SINGLE_SCENE)
    visibility = models.CharField(max_length=30, default=VISIBILITY_AUTHENTICATED)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_DRAFT, db_index=True)
    titiler_base_url = models.URLField(blank=True)
    cog_path = models.TextField(blank=True)
    mosaic_path = models.TextField(blank=True)
    source_dataset = models.ForeignKey(
        "imagery.ImageryDataset",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="published_services",
    )
    source_revision = models.PositiveIntegerField(null=True, blank=True)
    render_config = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="imagery_services")
    published_at = models.DateTimeField(null=True, blank=True)
    unpublished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]


class ImageryServiceAsset(models.Model):
    service = models.ForeignKey(ImageryService, on_delete=models.CASCADE, related_name="service_assets")
    imagery = models.ForeignKey("imagery.ImageryRecord", on_delete=models.PROTECT, related_name="published_services")
    asset_role = models.CharField(max_length=30, default="data")
    band_mapping = models.JSONField(default=dict, blank=True)
    order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order", "id"]
        constraints = [models.UniqueConstraint(fields=["service", "imagery"], name="unique_service_imagery")]


class ServicePublishJob(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [(value, value.title()) for value in [STATUS_PENDING, STATUS_RUNNING, STATUS_DONE, STATUS_FAILED]]

    service = models.ForeignKey(ImageryService, on_delete=models.CASCADE, related_name="publish_jobs")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    current_step = models.CharField(max_length=80, blank=True)
    progress = models.PositiveSmallIntegerField(default=0)
    error_message = models.TextField(blank=True)
    source_snapshot = models.JSONField(default=list, blank=True)
    target_revision = models.PositiveIntegerField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="service_publish_jobs")
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
