from django.conf import settings
from django.db import models


class IngestionJob(models.Model):
    SOURCE_URL_TEXT = "url_text"
    SOURCE_ZIP_UPLOAD = "zip_upload"
    SOURCE_ARCHIVE_UPLOAD = "archive_upload"
    SOURCE_FOLDER_ZIP = "folder_zip"
    SOURCE_FOLDER_UPLOAD = "folder_upload"
    SOURCE_STORAGE_REFERENCE = "storage_reference"
    SOURCE_TYPE_CHOICES = [
        (SOURCE_URL_TEXT, "URL text"),
        (SOURCE_ZIP_UPLOAD, "ZIP upload"),
        (SOURCE_ARCHIVE_UPLOAD, "Archive upload"),
        (SOURCE_FOLDER_ZIP, "Folder ZIP"),
        (SOURCE_FOLDER_UPLOAD, "Folder upload"),
        (SOURCE_STORAGE_REFERENCE, "Storage reference"),
    ]

    STATUS_PENDING = "pending"
    STATUS_VALIDATING = "validating"
    STATUS_RUNNING = "running"
    STATUS_SCANNING = "scanning"
    STATUS_PARSING = "parsing"
    STATUS_STORING = "storing"
    STATUS_DONE = "done"
    STATUS_FAILED = "failed"
    STATUS_CANCELED = "canceled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_VALIDATING, "Validating"),
        (STATUS_RUNNING, "Running"),
        (STATUS_SCANNING, "Scanning"),
        (STATUS_PARSING, "Parsing"),
        (STATUS_STORING, "Storing"),
        (STATUS_DONE, "Done"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELED, "Canceled"),
    ]

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ingestion_jobs")
    project = models.ForeignKey("projects.Project", null=True, blank=True, on_delete=models.PROTECT, related_name="ingestion_jobs")
    source_type = models.CharField(max_length=20, choices=SOURCE_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    total_count = models.PositiveIntegerField(default=0)
    success_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)
    skipped_count = models.PositiveIntegerField(default=0)
    warning_count = models.PositiveIntegerField(default=0)
    source_payload = models.JSONField(default=dict, blank=True)
    error_message = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"job:{self.id}:{self.status}"


class IngestionItem(models.Model):
    SOURCE_URL = "url"
    SOURCE_ARCHIVE_MEMBER = "archive_member"
    SOURCE_FILE = "file"
    SOURCE_FOLDER_FILE = "folder_file"
    SOURCE_KIND_CHOICES = [
        (SOURCE_URL, "URL"),
        (SOURCE_ARCHIVE_MEMBER, "Archive member"),
        (SOURCE_FILE, "File"),
        (SOURCE_FOLDER_FILE, "Folder file"),
    ]

    STATUS_PENDING = "pending"
    STATUS_DOWNLOADING = "downloading"
    STATUS_EXTRACTING = "extracting"
    STATUS_SCANNING = "scanning"
    STATUS_PARSING = "parsing"
    STATUS_STORING = "storing"
    STATUS_DONE = "done"
    STATUS_SKIPPED = "skipped"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_DOWNLOADING, "Downloading"),
        (STATUS_EXTRACTING, "Extracting"),
        (STATUS_SCANNING, "Scanning"),
        (STATUS_PARSING, "Parsing"),
        (STATUS_STORING, "Storing"),
        (STATUS_DONE, "Done"),
        (STATUS_SKIPPED, "Skipped"),
        (STATUS_FAILED, "Failed"),
    ]

    job = models.ForeignKey(IngestionJob, on_delete=models.CASCADE, related_name="items")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.CASCADE, related_name="children")
    container = models.BooleanField(default=False)
    source = models.TextField()
    source_kind = models.CharField(max_length=20, choices=SOURCE_KIND_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    raw_path = models.TextField(blank=True)
    cog_path = models.TextField(blank=True)
    stac_id = models.CharField(max_length=255, blank=True)
    image_id = models.CharField(max_length=64, blank=True)
    scene_key = models.CharField(max_length=255, blank=True)
    duplicate_of = models.ForeignKey(
        "imagery.ImageryRecord",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="duplicate_ingestion_items",
    )
    metadata_status = models.CharField(max_length=30, blank=True)
    relative_path = models.TextField(blank=True)
    error_message = models.TextField(blank=True)
    retry_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"item:{self.id}:{self.status}"
