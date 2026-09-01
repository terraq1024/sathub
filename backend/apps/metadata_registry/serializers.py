from rest_framework import serializers
from django.db import transaction

from .engine import validate_rules
from .models import MetadataOverride, MetadataSchema, MetadataSchemaField, MetadataQualityIssue, ParserRun, ParserTemplate, ParserTemplateVersion


class MetadataSchemaFieldSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetadataSchemaField
        fields = ["id", "key", "label", "data_type", "unit", "required", "searchable", "enum_values", "validation", "display_order"]
        read_only_fields = ["id"]


class MetadataSchemaSerializer(serializers.ModelSerializer):
    fields = MetadataSchemaFieldSerializer(many=True, required=False)

    class Meta:
        model = MetadataSchema
        fields = ["id", "code", "name", "version", "object_type", "description", "status", "created_by", "created_at", "updated_at", "fields"]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def validate(self, attrs):
        if self.instance and self.instance.status == MetadataSchema.STATUS_ACTIVE and attrs.get("status") == MetadataSchema.STATUS_DRAFT:
            raise serializers.ValidationError("active schemas cannot be reverted to draft")
        return attrs

    def create(self, validated_data):
        fields = validated_data.pop("fields", [])
        creator = validated_data.pop("created_by", None) or self.context["request"].user
        instance = MetadataSchema.objects.create(created_by=creator, **validated_data)
        MetadataSchemaField.objects.bulk_create([MetadataSchemaField(schema=instance, **field) for field in fields])
        return instance

    @transaction.atomic
    def update(self, instance, validated_data):
        fields = validated_data.pop("fields", None)
        instance = super().update(instance, validated_data)
        if fields is not None:
            instance.fields.all().delete()
            MetadataSchemaField.objects.bulk_create(
                [MetadataSchemaField(schema=instance, **field) for field in fields]
            )
        return instance


class ParserTemplateSerializer(serializers.ModelSerializer):
    schema_code = serializers.CharField(source="schema.code", read_only=True)

    class Meta:
        model = ParserTemplate
        fields = ["id", "schema", "schema_code", "name", "matcher", "priority", "status", "created_by", "created_at", "updated_at"]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]


class ParserTemplateVersionSerializer(serializers.ModelSerializer):
    template_name = serializers.CharField(source="template.name", read_only=True)

    class Meta:
        model = ParserTemplateVersion
        fields = ["id", "template", "template_name", "version", "rules", "status", "created_by", "published_by", "published_at", "created_at"]
        read_only_fields = ["id", "template", "status", "created_by", "published_by", "published_at", "created_at"]

    def validate_rules(self, value):
        try:
            return validate_rules(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def validate(self, attrs):
        if self.instance and self.instance.status == ParserTemplateVersion.STATUS_PUBLISHED:
            raise serializers.ValidationError("published versions are immutable; create a new version")
        return attrs


class ParserRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = ParserRun
        fields = ["id", "imagery", "parser_version", "status", "dry_run", "input_fingerprint", "values", "provenance", "warnings", "errors", "started_at", "finished_at"]


class MetadataQualityIssueSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetadataQualityIssue
        fields = ["id", "imagery", "parser_run", "field_key", "code", "severity", "message", "details", "status", "created_at", "resolved_at"]


class MetadataOverrideSerializer(serializers.ModelSerializer):
    class Meta:
        model = MetadataOverride
        fields = ["id", "imagery", "field_key", "value", "raw_value", "reason", "locked", "created_by", "created_at"]
        read_only_fields = ["id", "created_by", "created_at"]

    def validate_field_key(self, value):
        value = value.strip()
        if not value or not serializers.RegexField(regex=r"^[A-Za-z][A-Za-z0-9_.-]{0,119}$").run_validation(value):
            raise serializers.ValidationError("field_key must be a safe metadata field name")
        return value


class DryRunSerializer(serializers.Serializer):
    imagery_id = serializers.CharField(max_length=64)
    parser_version_id = serializers.IntegerField(required=False)
