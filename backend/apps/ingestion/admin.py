from django.contrib import admin

from .models import IngestionItem, IngestionJob


@admin.register(IngestionJob)
class IngestionJobAdmin(admin.ModelAdmin):
    list_display = ["id", "project", "created_by", "source_type", "status", "total_count", "success_count", "failed_count", "created_at"]
    list_filter = ["source_type", "status", "created_at"]
    search_fields = ["project__name", "project__code", "created_by__username"]


@admin.register(IngestionItem)
class IngestionItemAdmin(admin.ModelAdmin):
    list_display = ["id", "job", "source_kind", "status", "image_id", "stac_id", "retry_count", "created_at"]
    list_filter = ["source_kind", "status", "created_at"]
    search_fields = ["source", "raw_path", "image_id", "stac_id"]
