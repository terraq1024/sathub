import uuid
from django.conf import settings
from django.db import models


class DeliveryBasket(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="delivery_basket")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "delivery"


class DeliveryBasketItem(models.Model):
    basket = models.ForeignKey(DeliveryBasket, on_delete=models.CASCADE, related_name="items")
    imagery = models.ForeignKey("imagery.ImageryRecord", on_delete=models.CASCADE, related_name="delivery_items")
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "delivery"
        constraints = [models.UniqueConstraint(fields=["basket", "imagery"], name="unique_delivery_basket_imagery")]


class DeliverySnapshot(models.Model):
    STATUS_FROZEN = "frozen"
    STATUS_ARCHIVED = "archived"
    STATUS_CHOICES = [(STATUS_FROZEN, "Frozen"), (STATUS_ARCHIVED, "Archived")]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="delivery_snapshots")
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_FROZEN, db_index=True)
    imagery_ids = models.JSONField(default=list)
    manifest = models.JSONField(default=dict)
    frozen_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "delivery"
        ordering = ["-frozen_at"]


class ExportJob(models.Model):
    FORMAT_MANIFEST = "manifest"
    FORMAT_STAC = "stac"
    FORMAT_ZIP = "zip"
    FORMATS = [(FORMAT_MANIFEST, "Manifest"), (FORMAT_STAC, "STAC"), (FORMAT_ZIP, "ZIP")]
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"
    STATUSES = [(x, x.title()) for x in (STATUS_PENDING, STATUS_RUNNING, STATUS_DONE, STATUS_FAILED)]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="export_jobs")
    format = models.CharField(max_length=20, choices=FORMATS)
    status = models.CharField(max_length=20, choices=STATUSES, default=STATUS_PENDING, db_index=True)
    imagery_ids = models.JSONField(default=list)
    snapshot = models.ForeignKey(DeliverySnapshot, null=True, blank=True, on_delete=models.PROTECT, related_name="exports")
    file_path = models.TextField(blank=True)
    file_size = models.BigIntegerField(null=True, blank=True)
    error = models.TextField(blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "delivery"
