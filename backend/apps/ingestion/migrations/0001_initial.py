import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="IngestionJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source_type", models.CharField(choices=[("url_text", "URL text"), ("zip_upload", "ZIP upload"), ("folder_zip", "Folder ZIP")], max_length=20)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("running", "Running"), ("parsing", "Parsing"), ("storing", "Storing"), ("done", "Done"), ("failed", "Failed"), ("canceled", "Canceled")], default="pending", max_length=20)),
                ("total_count", models.PositiveIntegerField(default=0)),
                ("success_count", models.PositiveIntegerField(default=0)),
                ("failed_count", models.PositiveIntegerField(default=0)),
                ("source_payload", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ingestion_jobs", to=settings.AUTH_USER_MODEL)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="ingestion_jobs", to="projects.project")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
        migrations.CreateModel(
            name="IngestionItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.TextField()),
                ("source_kind", models.CharField(choices=[("url", "URL"), ("archive_member", "Archive member"), ("file", "File")], max_length=20)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("downloading", "Downloading"), ("extracting", "Extracting"), ("parsing", "Parsing"), ("storing", "Storing"), ("done", "Done"), ("failed", "Failed")], default="pending", max_length=20)),
                ("raw_path", models.TextField(blank=True)),
                ("cog_path", models.TextField(blank=True)),
                ("stac_id", models.CharField(blank=True, max_length=255)),
                ("image_id", models.CharField(blank=True, max_length=64)),
                ("error_message", models.TextField(blank=True)),
                ("retry_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="ingestion.ingestionjob")),
            ],
            options={"ordering": ["id"]},
        ),
    ]
