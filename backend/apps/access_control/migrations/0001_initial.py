from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True
    dependencies = [("auth", "0012_alter_user_first_name_max_length"), ("imagery", "0003_imageryrecord_archived_at_imageryrecord_archived_by_and_more")]
    operations = [migrations.CreateModel(name="ApiAccessToken", fields=[
        ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
        ("name", models.CharField(max_length=120)),
        ("token_prefix", models.CharField(db_index=True, max_length=16)),
        ("token_hash", models.CharField(max_length=64, unique=True)),
        ("scopes", models.JSONField(default=list)),
        ("expires_at", models.DateTimeField(blank=True, db_index=True, null=True)),
        ("revoked_at", models.DateTimeField(blank=True, db_index=True, null=True)),
        ("last_used_at", models.DateTimeField(blank=True, null=True)),
        ("created_at", models.DateTimeField(auto_now_add=True)),
        ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="api_access_tokens", to=settings.AUTH_USER_MODEL)),
    ], options={"ordering": ["-created_at"]})]
