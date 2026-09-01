import django.db.models.deletion
import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [("imagery", "0002_imageryrecord_archive_filename_and_more"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(name="ImageryService", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("name", models.CharField(max_length=255)), ("service_key", models.SlugField(max_length=80, unique=True)),
            ("service_type", models.CharField(default="single_scene", max_length=30)),
            ("visibility", models.CharField(default="authenticated", max_length=30)),
            ("status", models.CharField(db_index=True, default="draft", max_length=30)),
            ("titiler_base_url", models.URLField(blank=True)), ("cog_path", models.TextField(blank=True)),
            ("render_config", models.JSONField(blank=True, default=dict)), ("error_message", models.TextField(blank=True)),
            ("published_at", models.DateTimeField(blank=True, null=True)), ("unpublished_at", models.DateTimeField(blank=True, null=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="imagery_services", to=settings.AUTH_USER_MODEL)),
        ], options={"ordering": ["-created_at"]}),
        migrations.CreateModel(name="ImageryServiceAsset", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("asset_role", models.CharField(default="data", max_length=30)), ("band_mapping", models.JSONField(blank=True, default=dict)),
            ("order", models.PositiveIntegerField(default=0)),
            ("imagery", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="published_services", to="imagery.imageryrecord")),
            ("service", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="service_assets", to="publishing.imageryservice")),
        ], options={"ordering": ["order", "id"]}),
        migrations.CreateModel(name="ServicePublishJob", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("status", models.CharField(db_index=True, default="pending", max_length=20)), ("current_step", models.CharField(blank=True, max_length=80)),
            ("progress", models.PositiveSmallIntegerField(default=0)), ("error_message", models.TextField(blank=True)),
            ("started_at", models.DateTimeField(blank=True, null=True)), ("finished_at", models.DateTimeField(blank=True, null=True)),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="service_publish_jobs", to=settings.AUTH_USER_MODEL)),
            ("service", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="publish_jobs", to="publishing.imageryservice")),
        ], options={"ordering": ["-created_at"]}),
        migrations.AddConstraint(model_name="imageryserviceasset", constraint=models.UniqueConstraint(fields=("service", "imagery"), name="unique_service_imagery")),
    ]
