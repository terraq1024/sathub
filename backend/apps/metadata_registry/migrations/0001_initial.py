from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("imagery", "0004_imagerydataset_last_refreshed_at_and_more"),
    ]
    operations = [
        migrations.CreateModel(
            name="MetadataSchema",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.SlugField(max_length=100, unique=True)), ("name", models.CharField(max_length=200)), ("version", models.CharField(default="1.0.0", max_length=40)), ("object_type", models.CharField(default="imagery", max_length=40)), ("description", models.TextField(blank=True)), ("status", models.CharField(choices=[("draft", "Draft"), ("active", "Active"), ("retired", "Retired")], default="draft", max_length=20)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="metadata_schemas", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["code"]},
        ),
        migrations.CreateModel(
            name="ParserTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("name", models.CharField(max_length=200)), ("matcher", models.JSONField(default=dict)), ("priority", models.IntegerField(default=0)), ("status", models.CharField(choices=[("draft", "Draft"), ("active", "Active"), ("disabled", "Disabled")], default="draft", max_length=20)), ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="parser_templates", to=settings.AUTH_USER_MODEL)), ("schema", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="templates", to="metadata_registry.metadataschema")),
            ],
            options={"ordering": ["-priority", "name"], "constraints": [models.UniqueConstraint(fields=("schema", "name"), name="unique_parser_template_name")]},
        ),
        migrations.CreateModel(
            name="MetadataSchemaField",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("key", models.CharField(max_length=120)), ("label", models.CharField(blank=True, max_length=200)), ("data_type", models.CharField(choices=[("string", "string"), ("integer", "integer"), ("float", "float"), ("boolean", "boolean"), ("datetime", "datetime"), ("enum", "enum"), ("array", "array"), ("geometry", "geometry"), ("bbox", "bbox"), ("object", "object")], default="string", max_length=20)), ("unit", models.CharField(blank=True, max_length=40)), ("required", models.BooleanField(default=False)), ("searchable", models.BooleanField(default=False)), ("enum_values", models.JSONField(blank=True, default=list)), ("validation", models.JSONField(blank=True, default=dict)), ("display_order", models.PositiveIntegerField(default=0)),
                ("schema", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="fields", to="metadata_registry.metadataschema")),
            ],
            options={"ordering": ["display_order", "key"], "constraints": [models.UniqueConstraint(fields=("schema", "key"), name="unique_metadata_schema_field")]},
        ),
        migrations.CreateModel(
            name="ParserTemplateVersion",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("version", models.CharField(max_length=40)), ("rules", models.JSONField(default=dict)), ("status", models.CharField(choices=[("draft", "Draft"), ("published", "Published"), ("retired", "Retired")], default="draft", max_length=20)), ("published_at", models.DateTimeField(blank=True, null=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="parser_template_versions", to=settings.AUTH_USER_MODEL)), ("published_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="published_parser_versions", to=settings.AUTH_USER_MODEL)), ("template", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="versions", to="metadata_registry.parsertemplate")),
            ],
            options={"ordering": ["template", "-created_at"], "constraints": [models.UniqueConstraint(fields=("template", "version"), name="unique_parser_template_version")]},
        ),
        migrations.CreateModel(
            name="ParserRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("status", models.CharField(choices=[("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("dry_run", "Dry run")], default="running", max_length=20)), ("dry_run", models.BooleanField(default=False)), ("input_fingerprint", models.CharField(blank=True, max_length=64)), ("values", models.JSONField(blank=True, default=dict)), ("provenance", models.JSONField(blank=True, default=dict)), ("warnings", models.JSONField(blank=True, default=list)), ("errors", models.JSONField(blank=True, default=list)), ("started_at", models.DateTimeField(auto_now_add=True)), ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("imagery", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="metadata_parser_runs", to="imagery.imageryrecord")), ("parser_version", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="runs", to="metadata_registry.parsertemplateversion")),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.CreateModel(
            name="MetadataOverride",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("field_key", models.CharField(max_length=120)), ("value", models.JSONField()), ("raw_value", models.JSONField(blank=True, null=True)), ("reason", models.TextField(blank=True)), ("locked", models.BooleanField(default=True)), ("created_at", models.DateTimeField(auto_now_add=True)), ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="metadata_overrides", to=settings.AUTH_USER_MODEL)), ("imagery", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="metadata_overrides", to="imagery.imageryrecord")),
            ],
            options={"ordering": ["field_key", "-created_at"], "indexes": [models.Index(fields=["imagery", "field_key", "locked"], name="metadata_re_imagery_7d7c31_idx")]},
        ),
        migrations.CreateModel(
            name="MetadataQualityIssue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("field_key", models.CharField(blank=True, max_length=120)), ("code", models.CharField(max_length=80)), ("severity", models.CharField(choices=[("info", "Info"), ("warning", "Warning"), ("error", "Error")], default="warning", max_length=20)), ("message", models.TextField()), ("details", models.JSONField(blank=True, default=dict)), ("status", models.CharField(choices=[("open", "Open"), ("resolved", "Resolved")], default="open", max_length=20)), ("created_at", models.DateTimeField(auto_now_add=True)), ("resolved_at", models.DateTimeField(blank=True, null=True)),
                ("imagery", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="metadata_quality_issues", to="imagery.imageryrecord")), ("parser_run", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="quality_issues", to="metadata_registry.parserrun")),
            ],
            options={"ordering": ["-created_at"], "indexes": [models.Index(fields=["imagery", "status", "severity"], name="metadata_qu_imagery_b7bde1_idx")]},
        ),
    ]
