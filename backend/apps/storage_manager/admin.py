from django.contrib import admin

from .models import StorageEndpoint, StorageObject, StorageScanJob


@admin.register(StorageEndpoint)
class StorageEndpointAdmin(admin.ModelAdmin):
    list_display = ["name", "endpoint_type", "mode", "status", "enabled", "last_scan_at", "created_by"]
    list_filter = ["endpoint_type", "mode", "status", "enabled"]
    search_fields = ["name", "root_uri", "credential_ref"]
    readonly_fields = ["status", "status_message", "last_check_at", "last_scan_at", "created_at", "updated_at"]


@admin.register(StorageScanJob)
class StorageScanJobAdmin(admin.ModelAdmin):
    list_display = ["id", "endpoint", "mode", "status", "files_scanned", "new_count", "changed_count", "missing_count", "created_at"]
    list_filter = ["mode", "status", "created_at"]
    search_fields = ["endpoint__name", "error_message", "created_by__username"]
    readonly_fields = ["checkpoint", "started_at", "finished_at", "created_at"]


@admin.register(StorageObject)
class StorageObjectAdmin(admin.ModelAdmin):
    list_display = ["object_key", "endpoint", "scene_stem", "scene_role", "status", "size_bytes", "modified_at", "missing_confirmed"]
    list_filter = ["scene_role", "status", "missing_confirmed"]
    search_fields = ["object_key", "scene_stem", "scene_group_key"]
    readonly_fields = ["endpoint", "object_key", "fingerprint", "checksum_sha256", "source_metadata", "first_seen_at", "last_seen_at", "last_verified_at"]
