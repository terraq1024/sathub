from django.contrib import admin

from .models import MetadataQualityIssue, MetadataSchema, MetadataSchemaField, MetadataOverride, ParserRun, ParserTemplate, ParserTemplateVersion


@admin.register(MetadataSchema)
class MetadataSchemaAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "version", "status", "updated_at")
    search_fields = ("code", "name")


@admin.register(MetadataSchemaField)
class MetadataSchemaFieldAdmin(admin.ModelAdmin):
    list_display = ("schema", "key", "data_type", "required", "searchable")
    list_filter = ("data_type", "required", "searchable")
    search_fields = ("schema__code", "key")


@admin.register(ParserTemplate)
class ParserTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "schema", "priority", "status", "updated_at")
    list_filter = ("status", "schema")
    search_fields = ("name", "schema__code")


@admin.register(ParserTemplateVersion)
class ParserTemplateVersionAdmin(admin.ModelAdmin):
    list_display = ("template", "version", "status", "published_at")
    list_filter = ("status", "template")
    readonly_fields = ("published_at", "published_by")


@admin.register(ParserRun)
class ParserRunAdmin(admin.ModelAdmin):
    list_display = ("id", "imagery", "parser_version", "status", "dry_run", "started_at", "finished_at")
    list_filter = ("status", "dry_run")
    readonly_fields = ("started_at", "finished_at")


@admin.register(MetadataOverride)
class MetadataOverrideAdmin(admin.ModelAdmin):
    list_display = ("imagery", "field_key", "locked", "created_by", "created_at")
    search_fields = ("imagery__scene_key", "field_key")


@admin.register(MetadataQualityIssue)
class MetadataQualityIssueAdmin(admin.ModelAdmin):
    list_display = ("imagery", "field_key", "code", "severity", "status", "created_at")
    list_filter = ("severity", "status", "code")
    search_fields = ("imagery__scene_key", "field_key", "message")

