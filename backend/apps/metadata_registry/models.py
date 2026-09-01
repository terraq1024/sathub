from django.conf import settings
from django.db import models


class MetadataSchema(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_ACTIVE = "active"
    STATUS_RETIRED = "retired"
    STATUS_CHOICES = [(STATUS_DRAFT, "Draft"), (STATUS_ACTIVE, "Active"), (STATUS_RETIRED, "Retired")]

    code = models.SlugField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    version = models.CharField(max_length=40, default="1.0.0")
    object_type = models.CharField(max_length=40, default="imagery")
    description = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="metadata_schemas")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "metadata_registry"
        ordering = ["code"]

    def __str__(self):
        return f"{self.code}@{self.version}"


class MetadataSchemaField(models.Model):
    TYPE_CHOICES = [(value, value) for value in ("string", "integer", "float", "boolean", "datetime", "enum", "array", "geometry", "bbox", "object")]

    schema = models.ForeignKey(MetadataSchema, on_delete=models.CASCADE, related_name="fields")
    key = models.CharField(max_length=120)
    label = models.CharField(max_length=200, blank=True)
    data_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default="string")
    unit = models.CharField(max_length=40, blank=True)
    required = models.BooleanField(default=False)
    searchable = models.BooleanField(default=False)
    enum_values = models.JSONField(default=list, blank=True)
    validation = models.JSONField(default=dict, blank=True)
    display_order = models.PositiveIntegerField(default=0)

    class Meta:
        app_label = "metadata_registry"
        ordering = ["display_order", "key"]
        constraints = [models.UniqueConstraint(fields=["schema", "key"], name="unique_metadata_schema_field")]

    def __str__(self):
        return f"{self.schema.code}.{self.key}"


class ParserTemplate(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_ACTIVE = "active"
    STATUS_DISABLED = "disabled"
    STATUS_CHOICES = [(STATUS_DRAFT, "Draft"), (STATUS_ACTIVE, "Active"), (STATUS_DISABLED, "Disabled")]

    schema = models.ForeignKey(MetadataSchema, on_delete=models.PROTECT, related_name="templates")
    name = models.CharField(max_length=200)
    matcher = models.JSONField(default=dict)
    priority = models.IntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="parser_templates")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "metadata_registry"
        ordering = ["-priority", "name"]
        constraints = [models.UniqueConstraint(fields=["schema", "name"], name="unique_parser_template_name")]

    def __str__(self):
        return self.name


class ParserTemplateVersion(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_PUBLISHED = "published"
    STATUS_RETIRED = "retired"
    STATUS_CHOICES = [(STATUS_DRAFT, "Draft"), (STATUS_PUBLISHED, "Published"), (STATUS_RETIRED, "Retired")]

    template = models.ForeignKey(ParserTemplate, on_delete=models.CASCADE, related_name="versions")
    version = models.CharField(max_length=40)
    rules = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="parser_template_versions")
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="published_parser_versions")
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "metadata_registry"
        ordering = ["template", "-created_at"]
        constraints = [models.UniqueConstraint(fields=["template", "version"], name="unique_parser_template_version")]

    def __str__(self):
        return f"{self.template.name}@{self.version}"

    def save(self, *args, **kwargs):
        if self.pk:
            previous = type(self).objects.filter(pk=self.pk).values_list("status", flat=True).first()
            if previous == self.STATUS_PUBLISHED:
                raise ValueError("published parser template versions are immutable")
        super().save(*args, **kwargs)


class ParserRun(models.Model):
    STATUS_RUNNING = "running"
    STATUS_SUCCEEDED = "succeeded"
    STATUS_FAILED = "failed"
    STATUS_DRY_RUN = "dry_run"
    STATUS_CHOICES = [(STATUS_RUNNING, "Running"), (STATUS_SUCCEEDED, "Succeeded"), (STATUS_FAILED, "Failed"), (STATUS_DRY_RUN, "Dry run")]

    imagery = models.ForeignKey("imagery.ImageryRecord", null=True, blank=True, on_delete=models.CASCADE, related_name="metadata_parser_runs")
    parser_version = models.ForeignKey(ParserTemplateVersion, null=True, blank=True, on_delete=models.SET_NULL, related_name="runs")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RUNNING)
    dry_run = models.BooleanField(default=False)
    input_fingerprint = models.CharField(max_length=64, blank=True)
    values = models.JSONField(default=dict, blank=True)
    provenance = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    errors = models.JSONField(default=list, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "metadata_registry"
        ordering = ["-started_at"]


class MetadataOverride(models.Model):
    imagery = models.ForeignKey("imagery.ImageryRecord", on_delete=models.CASCADE, related_name="metadata_overrides")
    field_key = models.CharField(max_length=120)
    value = models.JSONField()
    raw_value = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)
    locked = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="metadata_overrides")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        app_label = "metadata_registry"
        ordering = ["field_key", "-created_at"]
        indexes = [models.Index(fields=["imagery", "field_key", "locked"], name="metadata_re_imagery_7d7c31_idx")]


class MetadataQualityIssue(models.Model):
    SEVERITY_INFO = "info"
    SEVERITY_WARNING = "warning"
    SEVERITY_ERROR = "error"
    SEVERITY_CHOICES = [(SEVERITY_INFO, "Info"), (SEVERITY_WARNING, "Warning"), (SEVERITY_ERROR, "Error")]
    STATUS_OPEN = "open"
    STATUS_RESOLVED = "resolved"
    STATUS_CHOICES = [(STATUS_OPEN, "Open"), (STATUS_RESOLVED, "Resolved")]

    imagery = models.ForeignKey("imagery.ImageryRecord", null=True, blank=True, on_delete=models.CASCADE, related_name="metadata_quality_issues")
    parser_run = models.ForeignKey(ParserRun, null=True, blank=True, on_delete=models.CASCADE, related_name="quality_issues")
    field_key = models.CharField(max_length=120, blank=True)
    code = models.CharField(max_length=80)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default=SEVERITY_WARNING)
    message = models.TextField()
    details = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_OPEN)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "metadata_registry"
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["imagery", "status", "severity"], name="metadata_qu_imagery_b7bde1_idx")]
