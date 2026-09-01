from django.conf import settings
from django.db import models


class AdministrativeUnit(models.Model):
    LEVEL_PROVINCE = "province"
    LEVEL_CITY = "city"
    LEVEL_COUNTY = "county"
    LEVEL_CHOICES = (
        (LEVEL_PROVINCE, "Province"),
        (LEVEL_CITY, "City"),
        (LEVEL_COUNTY, "County"),
    )

    level = models.CharField(max_length=20, choices=LEVEL_CHOICES, db_index=True)
    code = models.CharField(max_length=32, db_index=True)
    name = models.CharField(max_length=120, db_index=True)
    parent = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="children"
    )
    geometry = models.JSONField()
    bbox = models.JSONField()
    source_version = models.CharField(max_length=120, db_index=True)
    source_file = models.CharField(max_length=255, blank=True)
    is_valid = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["level", "code", "name"]
        constraints = [
            models.UniqueConstraint(fields=["level", "code", "source_version"], name="unique_admin_unit_version_code"),
        ]
        indexes = [models.Index(fields=["parent", "level"])]

    def __str__(self):
        return f"{self.name} ({self.code})"


class ImageryAdministrativeUnit(models.Model):
    RELATION_INTERSECTS = "intersects"
    RELATION_CONTAINS = "contains"
    RELATION_CENTER_INSIDE = "center_inside"
    RELATION_CHOICES = (
        (RELATION_INTERSECTS, "Intersects"),
        (RELATION_CONTAINS, "Contains"),
        (RELATION_CENTER_INSIDE, "Center inside"),
    )

    imagery = models.ForeignKey(
        "imagery.ImageryRecord", on_delete=models.CASCADE, related_name="administrative_units"
    )
    administrative_unit = models.ForeignKey(
        AdministrativeUnit, on_delete=models.PROTECT, related_name="imagery_links"
    )
    relation = models.CharField(max_length=20, choices=RELATION_CHOICES, default=RELATION_INTERSECTS)
    coverage_ratio = models.FloatField(null=True, blank=True)
    primary = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["imagery", "administrative_unit"], name="unique_imagery_admin_unit"),
        ]
        indexes = [models.Index(fields=["administrative_unit", "primary"])]

    def __str__(self):
        return f"{self.imagery_id}:{self.administrative_unit_id}"


class Classification(models.Model):
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=120, blank=True)
    description = models.TextField(blank=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    enabled = models.BooleanField(default=True, db_index=True)
    sort_order = models.IntegerField(default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_catalog_classifications")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sort_order", "name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["parent", "name"], name="unique_classification_sibling_name"),
        ]

    def __str__(self):
        return self.name


class Tag(models.Model):
    name = models.CharField(max_length=80, unique=True)
    color = models.CharField(max_length=20, default="#1677ff")
    description = models.TextField(blank=True)
    enabled = models.BooleanField(default=True, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_catalog_tags")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


class ImageryClassification(models.Model):
    SOURCE_MANUAL = "manual"
    SOURCE_RULE = "rule"
    SOURCE_PARSER = "parser"
    SOURCE_CHOICES = ((SOURCE_MANUAL, "Manual"), (SOURCE_RULE, "Rule"), (SOURCE_PARSER, "Parser"))

    imagery = models.ForeignKey("imagery.ImageryRecord", on_delete=models.CASCADE, related_name="classifications")
    classification = models.ForeignKey(Classification, on_delete=models.CASCADE, related_name="imagery_links")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_MANUAL)
    confidence = models.FloatField(null=True, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="imagery_classification_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["imagery", "classification"], name="unique_imagery_classification")]


class DatasetClassification(models.Model):
    dataset = models.ForeignKey("imagery.ImageryDataset", on_delete=models.CASCADE, related_name="classifications")
    classification = models.ForeignKey(Classification, on_delete=models.CASCADE, related_name="dataset_links")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="dataset_classification_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["dataset", "classification"], name="unique_dataset_classification")]


class ImageryTag(models.Model):
    imagery = models.ForeignKey("imagery.ImageryRecord", on_delete=models.CASCADE, related_name="catalog_tags")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="imagery_links")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="imagery_tag_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["imagery", "tag"], name="unique_imagery_tag")]


class DatasetTag(models.Model):
    dataset = models.ForeignKey("imagery.ImageryDataset", on_delete=models.CASCADE, related_name="catalog_tags")
    tag = models.ForeignKey(Tag, on_delete=models.CASCADE, related_name="dataset_links")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="dataset_tag_links")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["dataset", "tag"], name="unique_dataset_tag")]
