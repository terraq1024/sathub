import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class StorageEndpoint(models.Model):
    TYPE_LOCAL = "local_directory"
    TYPE_NAS = "nas_smb"
    TYPE_S3 = "s3"
    TYPE_SFTP = "sftp"
    TYPE_FTP = "ftp"
    TYPE_CHOICES = [
        (TYPE_LOCAL, "本地目录"),
        (TYPE_NAS, "NAS/SMB"),
        (TYPE_S3, "S3"),
        (TYPE_SFTP, "SFTP"),
        (TYPE_FTP, "FTP"),
    ]

    MODE_REFERENCE = "reference"
    MODE_MANAGED = "managed"
    MODE_CHOICES = [(MODE_REFERENCE, "引用"), (MODE_MANAGED, "托管")]

    STATUS_CONFIGURED = "configured"
    STATUS_ONLINE = "online"
    STATUS_DEGRADED = "degraded"
    STATUS_OFFLINE = "offline"
    STATUS_PERMISSION_DENIED = "permission_denied"
    STATUS_ERROR = "error"
    STATUS_CHOICES = [
        (STATUS_CONFIGURED, "已配置"),
        (STATUS_ONLINE, "在线"),
        (STATUS_DEGRADED, "降级"),
        (STATUS_OFFLINE, "离线"),
        (STATUS_PERMISSION_DENIED, "无权限"),
        (STATUS_ERROR, "错误"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    endpoint_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_REFERENCE)
    root_uri = models.TextField()
    credential_ref = models.CharField(max_length=255, blank=True)
    read_only = models.BooleanField(default=True)
    enabled = models.BooleanField(default=True)
    scan_policy = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default=STATUS_CONFIGURED)
    status_message = models.TextField(blank=True)
    last_check_at = models.DateTimeField(null=True, blank=True)
    last_scan_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="storage_endpoints",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "created_at"]
        indexes = [models.Index(fields=["endpoint_type", "status"])]

    def clean(self):
        if not self.name.strip():
            raise ValidationError({"name": "存储源名称不能为空。"})
        if self.endpoint_type in {self.TYPE_LOCAL, self.TYPE_NAS}:
            from .backends import validate_local_root

            validate_local_root(self.root_uri)
        elif self.endpoint_type in {self.TYPE_S3, self.TYPE_SFTP, self.TYPE_FTP}:
            raise ValidationError({"endpoint_type": "当前版本仅支持本地目录和 NAS/SMB。"})

    def __str__(self):
        return self.name

    @property
    def root_name(self):
        value = self.root_uri.replace("\\", "/").rstrip("/")
        return value.rsplit("/", 1)[-1] or value


class StorageScanJob(models.Model):
    MODE_FULL = "full"
    MODE_INCREMENTAL = "incremental"
    MODE_HEALTH_CHECK = "health_check"
    MODE_CHOICES = [
        (MODE_FULL, "全量扫描"),
        (MODE_INCREMENTAL, "增量扫描"),
        (MODE_HEALTH_CHECK, "连接检查"),
    ]
    STATUS_PENDING = "pending"
    STATUS_RUNNING = "running"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_CHOICES = [
        (STATUS_PENDING, "待执行"),
        (STATUS_RUNNING, "执行中"),
        (STATUS_SUCCEEDED, "成功"),
        (STATUS_FAILED, "失败"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    endpoint = models.ForeignKey(StorageEndpoint, on_delete=models.CASCADE, related_name="scan_jobs")
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default=MODE_INCREMENTAL)
    prefix = models.CharField(max_length=1024, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    checkpoint = models.JSONField(default=dict, blank=True)
    files_scanned = models.PositiveIntegerField(default=0)
    scenes_found = models.PositiveIntegerField(default=0)
    new_count = models.PositiveIntegerField(default=0)
    changed_count = models.PositiveIntegerField(default=0)
    missing_count = models.PositiveIntegerField(default=0)
    unchanged_count = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="storage_scan_jobs",
    )
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["endpoint", "status", "created_at"])]

    def __str__(self):
        return f"{self.endpoint.name} / {self.mode} / {self.status}"


class StorageObject(models.Model):
    STATUS_NEW = "new"
    STATUS_CHANGED = "changed"
    STATUS_MISSING = "missing"
    STATUS_UNCHANGED = "unchanged"
    STATUS_CHOICES = [
        (STATUS_NEW, "新增"),
        (STATUS_CHANGED, "已变化"),
        (STATUS_MISSING, "缺失"),
        (STATUS_UNCHANGED, "未变化"),
    ]
    ROLE_DATA = "data"
    ROLE_PREVIEW = "preview"
    ROLE_THUMBNAIL = "thumbnail"
    ROLE_METADATA = "metadata"
    ROLE_INCIDENCE = "incidence"
    ROLE_RESULT = "result"
    ROLE_LOG = "log"
    ROLE_OTHER = "other"
    ROLE_CHOICES = [
        (ROLE_DATA, "主数据"),
        (ROLE_PREVIEW, "预览图"),
        (ROLE_THUMBNAIL, "缩略图"),
        (ROLE_METADATA, "元数据"),
        (ROLE_INCIDENCE, "入射角"),
        (ROLE_RESULT, "结果元数据"),
        (ROLE_LOG, "日志"),
        (ROLE_OTHER, "其他"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    endpoint = models.ForeignKey(StorageEndpoint, on_delete=models.CASCADE, related_name="storage_objects")
    object_key = models.CharField(max_length=1024)
    scene_stem = models.CharField(max_length=512, blank=True, db_index=True)
    scene_group_key = models.CharField(max_length=1024, blank=True, db_index=True)
    scene_role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_OTHER)
    size_bytes = models.PositiveBigIntegerField(default=0)
    modified_at = models.DateTimeField(null=True, blank=True)
    fingerprint = models.CharField(max_length=200, blank=True)
    checksum_sha256 = models.CharField(max_length=64, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW, db_index=True)
    missing_scan_count = models.PositiveSmallIntegerField(default=0)
    missing_confirmed = models.BooleanField(default=False)
    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    last_verified_at = models.DateTimeField(null=True, blank=True)
    last_seen_scan = models.ForeignKey(
        StorageScanJob,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="seen_objects",
    )
    source_metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["object_key"]
        constraints = [
            models.UniqueConstraint(fields=["endpoint", "object_key"], name="unique_storage_endpoint_object_key"),
        ]
        indexes = [
            models.Index(fields=["endpoint", "status"]),
            models.Index(fields=["endpoint", "scene_group_key"]),
        ]

    def clean(self):
        from .backends import validate_object_key

        validate_object_key(self.object_key)

    def __str__(self):
        return f"{self.endpoint.name}: {self.object_key}"
