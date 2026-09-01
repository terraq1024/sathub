import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("imagery", "0004_imagerydataset_last_refreshed_at_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProcessingJob",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "等待处理"),
                            ("running", "处理中"),
                            ("succeeded", "处理成功"),
                            ("failed", "处理失败"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                (
                    "crop_geometry_type",
                    models.CharField(
                        choices=[("bbox", "边界框"), ("polygon", "多边形")],
                        max_length=20,
                    ),
                ),
                ("bbox", models.JSONField(blank=True, null=True)),
                ("geometry", models.JSONField(blank=True, null=True)),
                ("bands", models.JSONField(blank=True, default=list)),
                ("expression", models.CharField(blank=True, max_length=500)),
                (
                    "output_format",
                    models.CharField(
                        choices=[("geotiff", "GeoTIFF"), ("png", "PNG")],
                        default="geotiff",
                        max_length=20,
                    ),
                ),
                ("output_path", models.TextField(blank=True)),
                ("output_media_type", models.CharField(blank=True, max_length=120)),
                ("error_message", models.TextField(blank=True)),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="processing_jobs",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "imagery",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="processing_jobs",
                        to="imagery.imageryrecord",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at", "-updated_at"],
                "indexes": [
                    models.Index(
                        fields=["created_by", "status"],
                        name="processingj_created_8a1d1b_idx",
                    ),
                    models.Index(
                        fields=["imagery", "status"],
                        name="processingj_imagery_5f3d4f_idx",
                    ),
                ],
            },
        ),
    ]
