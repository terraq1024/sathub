from django.contrib import admin

from .models import ImageryAsset, ImageryDataset, ImageryDatasetMember, ImageryProjectTag, ImageryRecord


@admin.register(ImageryRecord)
class ImageryRecordAdmin(admin.ModelAdmin):
    list_display = ["scene_key", "display_name", "satellite_name", "imaging_mode", "polarization", "acquisition_time", "preview_status", "status", "is_archived"]
    list_filter = ["platform_code", "imaging_mode", "polarization", "product_level", "preview_status", "status", "is_archived"]
    search_fields = ["scene_key", "source_name", "display_name", "satellite_name", "stac_id"]


@admin.register(ImageryAsset)
class ImageryAssetAdmin(admin.ModelAdmin):
    list_display = ["imagery", "role", "name", "size_bytes", "created_at"]
    list_filter = ["role"]
    search_fields = ["imagery__scene_key", "name", "path"]


@admin.register(ImageryProjectTag)
class ImageryProjectTagAdmin(admin.ModelAdmin):
    list_display = ["imagery", "project", "created_at"]
    list_filter = ["project"]
    search_fields = ["imagery__scene_key", "project__name"]


class ImageryDatasetMemberInline(admin.TabularInline):
    model = ImageryDatasetMember
    extra = 0
    ordering = ["position"]


@admin.register(ImageryDataset)
class ImageryDatasetAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "revision", "created_by", "updated_at"]
    list_filter = ["status"]
    search_fields = ["name", "description", "created_by__username"]
    inlines = [ImageryDatasetMemberInline]
