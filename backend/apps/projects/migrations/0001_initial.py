import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Project",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                ("code", models.SlugField(max_length=80, unique=True)),
                ("description", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "created_by",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="created_projects", to=settings.AUTH_USER_MODEL),
                ),
            ],
            options={"ordering": ["name", "id"]},
        ),
        migrations.CreateModel(
            name="ProjectMembership",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("role", models.CharField(choices=[("owner", "Owner"), ("member", "Member"), ("viewer", "Viewer")], default="member", max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("project", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="memberships", to="projects.project")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="project_memberships", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["project_id", "user_id"]},
        ),
        migrations.AddConstraint(
            model_name="projectmembership",
            constraint=models.UniqueConstraint(fields=("project", "user"), name="unique_project_membership"),
        ),
    ]
