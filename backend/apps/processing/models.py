import uuid

from django.conf import settings
from django.db import models


class ProcessingJob(models.Model):
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "等待处理"),
        (STATUS_RUNNING, "处理中"),
        (STATUS_SUCCEEDED, "处理成功"),
        (STATUS_FAILED, "处理失败"),
    ]

    OUTPUT_GEOTIFF = "geotiff"
    OUTPUT_PNG = "png"
    OUTPUT_CHOICES = [
        (OUTPUT_GEOTIFF, "GeoTIFF"),
        (OUTPUT_PNG, "PNG"),
    ]

    CROP_BBOX = "bbox"
    CROP_POLYGON = "polygon"
    CROP_CHOICES = [
        (CROP_BBOX, "边界框"),
        (CROP_POLYGON, "多边形"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    imagery = models.ForeignKey(
        "imagery.ImageryRecord",
        on_delete=models.PROTECT,
        related_name="processing_jobs",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="processing_jobs",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_PENDING,
        db_index=True,
    )
    crop_geometry_type = models.CharField(max_length=20, choices=CROP_CHOICES)
    bbox = models.JSONField(null=True, blank=True)
    geometry = models.JSONField(null=True, blank=True)
    bands = models.JSONField(default=list, blank=True)
    expression = models.CharField(max_length=500, blank=True)
    output_format = models.CharField(
        max_length=20,
        choices=OUTPUT_CHOICES,
        default=OUTPUT_GEOTIFF,
    )
    output_path = models.TextField(blank=True)
    output_media_type = models.CharField(max_length=120, blank=True)
    error_message = models.TextField(blank=True)
    attempts = models.PositiveIntegerField(default=0)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-updated_at"]
        indexes = [
            models.Index(
                fields=["created_by", "status"],
                name="processingj_created_8a1d1b_idx",
            ),
            models.Index(
                fields=["imagery", "status"],
                name="processingj_imagery_5f3d4f_idx",
            ),
        ]

    def can_manage(self, user):
        return bool(
            user
            and user.is_authenticated
            and (
                user.is_staff
                or user.is_superuser
                or user.pk == self.created_by_id
            )
        )
