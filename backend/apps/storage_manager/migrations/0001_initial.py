from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True
    dependencies = [migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.CreateModel(
            name="StorageEndpoint",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("name", models.CharField(max_length=255)),
                ("endpoint_type", models.CharField(choices=[("local_directory", "本地目录"), ("nas_smb", "NAS/SMB"), ("s3", "S3"), ("sftp", "SFTP"), ("ftp", "FTP")], max_length=30)),
                ("mode", models.CharField(choices=[("reference", "引用"), ("managed", "托管")], default="reference", max_length=20)),
                ("root_uri", models.TextField()),
                ("credential_ref", models.CharField(blank=True, max_length=255)),
                ("read_only", models.BooleanField(default=True)),
                ("enabled", models.BooleanField(default=True)),
                ("scan_policy", models.JSONField(blank=True, default=dict)),
                ("status", models.CharField(choices=[("configured", "已配置"), ("online", "在线"), ("degraded", "降级"), ("offline", "离线"), ("permission_denied", "无权限"), ("error", "错误")], default="configured", max_length=30)),
                ("status_message", models.TextField(blank=True)),
                ("last_check_at", models.DateTimeField(blank=True, null=True)),
                ("last_scan_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="storage_endpoints", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name", "created_at"], "indexes": [models.Index(fields=["endpoint_type", "status"], name="storage_man_endpoin_74d384_idx")]},
        ),
        migrations.CreateModel(
            name="StorageScanJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("mode", models.CharField(choices=[("full", "全量扫描"), ("incremental", "增量扫描"), ("health_check", "连接检查")], default="incremental", max_length=20)),
                ("prefix", models.CharField(blank=True, max_length=1024)),
                ("status", models.CharField(choices=[("pending", "待执行"), ("running", "执行中"), ("succeeded", "成功"), ("failed", "失败")], default="pending", max_length=20)),
                ("checkpoint", models.JSONField(blank=True, default=dict)),
                ("files_scanned", models.PositiveIntegerField(default=0)),
                ("scenes_found", models.PositiveIntegerField(default=0)),
                ("new_count", models.PositiveIntegerField(default=0)),
                ("changed_count", models.PositiveIntegerField(default=0)),
                ("missing_count", models.PositiveIntegerField(default=0)),
                ("unchanged_count", models.PositiveIntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="storage_scan_jobs", to=settings.AUTH_USER_MODEL)),
                ("endpoint", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="scan_jobs", to="storage_manager.storageendpoint")),
            ],
            options={"ordering": ["-created_at"], "indexes": [models.Index(fields=["endpoint", "status", "created_at"], name="storage_man_endpoin_d96e44_idx")]},
        ),
        migrations.CreateModel(
            name="StorageObject",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("object_key", models.CharField(max_length=1024)),
                ("scene_stem", models.CharField(blank=True, db_index=True, max_length=512)),
                ("scene_group_key", models.CharField(blank=True, db_index=True, max_length=1024)),
                ("scene_role", models.CharField(choices=[("data", "主数据"), ("preview", "预览图"), ("thumbnail", "缩略图"), ("metadata", "元数据"), ("incidence", "入射角"), ("result", "结果元数据"), ("log", "日志"), ("other", "其他")], default="other", max_length=20)),
                ("size_bytes", models.PositiveBigIntegerField(default=0)),
                ("modified_at", models.DateTimeField(blank=True, null=True)),
                ("fingerprint", models.CharField(blank=True, max_length=200)),
                ("checksum_sha256", models.CharField(blank=True, max_length=64)),
                ("status", models.CharField(choices=[("new", "新增"), ("changed", "已变化"), ("missing", "缺失"), ("unchanged", "未变化")], db_index=True, default="new", max_length=20)),
                ("missing_scan_count", models.PositiveSmallIntegerField(default=0)),
                ("missing_confirmed", models.BooleanField(default=False)),
                ("first_seen_at", models.DateTimeField(auto_now_add=True)),
                ("last_seen_at", models.DateTimeField(blank=True, null=True)),
                ("last_verified_at", models.DateTimeField(blank=True, null=True)),
                ("source_metadata", models.JSONField(blank=True, default=dict)),
                ("endpoint", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="storage_objects", to="storage_manager.storageendpoint")),
                ("last_seen_scan", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="seen_objects", to="storage_manager.storagescanjob")),
            ],
            options={"ordering": ["object_key"], "indexes": [models.Index(fields=["endpoint", "status"], name="storage_man_endpoin_aa7a1e_idx"), models.Index(fields=["endpoint", "scene_group_key"], name="storage_man_endpoin_029318_idx")], "constraints": [models.UniqueConstraint(fields=("endpoint", "object_key"), name="unique_storage_endpoint_object_key")]},
        ),
    ]
