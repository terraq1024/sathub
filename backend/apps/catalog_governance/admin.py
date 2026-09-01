from django.contrib import admin

from .models import (
    AdministrativeUnit,
    Classification,
    DatasetClassification,
    DatasetTag,
    ImageryAdministrativeUnit,
    ImageryClassification,
    ImageryTag,
    Tag,
)


@admin.register(AdministrativeUnit)
class AdministrativeUnitAdmin(admin.ModelAdmin):
    list_display = ["name", "level", "code", "parent", "source_version", "is_valid"]
    list_filter = ["level", "source_version", "is_valid"]
    search_fields = ["name", "code"]


@admin.register(ImageryAdministrativeUnit)
class ImageryAdministrativeUnitAdmin(admin.ModelAdmin):
    list_display = ["imagery", "administrative_unit", "relation", "coverage_ratio", "primary"]
    list_filter = ["relation", "primary"]
    search_fields = ["imagery__scene_key", "administrative_unit__name", "administrative_unit__code"]


@admin.register(Classification)
class ClassificationAdmin(admin.ModelAdmin):
    list_display = ["name", "code", "parent", "enabled", "sort_order"]
    list_filter = ["enabled"]
    search_fields = ["name", "code", "description"]


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ["name", "color", "enabled", "created_by", "updated_at"]
    list_filter = ["enabled"]
    search_fields = ["name", "description"]


admin.site.register([ImageryClassification, DatasetClassification, ImageryTag, DatasetTag])
