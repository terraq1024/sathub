# Generated manually because this app is intentionally not added to the root settings in this change.
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("imagery", "0004_imagerydataset_last_refreshed_at_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="AdministrativeUnit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("level", models.CharField(choices=[("province", "Province"), ("city", "City"), ("county", "County")], db_index=True, max_length=20)),
                ("code", models.CharField(db_index=True, max_length=32)),
                ("name", models.CharField(db_index=True, max_length=120)),
                ("geometry", models.JSONField()),
                ("bbox", models.JSONField()),
                ("source_version", models.CharField(db_index=True, max_length=120)),
                ("source_file", models.CharField(blank=True, max_length=255)),
                ("is_valid", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="children", to="catalog_governance.administrativeunit")),
            ],
            options={
                "ordering": ["level", "code", "name"],
                "indexes": [models.Index(fields=["parent", "level"], name="catalog_gov_parent__c17e16_idx")],
            },
        ),
        migrations.CreateModel(
            name="Classification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("code", models.SlugField(blank=True, max_length=120)),
                ("description", models.TextField(blank=True)),
                ("enabled", models.BooleanField(db_index=True, default=True)),
                ("sort_order", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_catalog_classifications", to=settings.AUTH_USER_MODEL)),
                ("parent", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="children", to="catalog_governance.classification")),
            ],
            options={
                "ordering": ["sort_order", "name", "id"],
            },
        ),
        migrations.CreateModel(
            name="Tag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=80, unique=True)),
                ("color", models.CharField(default="#1677ff", max_length=20)),
                ("description", models.TextField(blank=True)),
                ("enabled", models.BooleanField(db_index=True, default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="created_catalog_tags", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["name", "id"]},
        ),
        migrations.CreateModel(
            name="ImageryAdministrativeUnit",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("relation", models.CharField(choices=[("intersects", "Intersects"), ("contains", "Contains"), ("center_inside", "Center inside")], default="intersects", max_length=20)),
                ("coverage_ratio", models.FloatField(blank=True, null=True)),
                ("primary", models.BooleanField(default=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("administrative_unit", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="imagery_links", to="catalog_governance.administrativeunit")),
                ("imagery", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="administrative_units", to="imagery.imageryrecord")),
            ],
            options={"indexes": [models.Index(fields=["administrative_unit", "primary"], name="catalog_gov_adminis_ee7dd1_idx")]},
        ),
        migrations.CreateModel(
            name="DatasetClassification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("classification", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dataset_links", to="catalog_governance.classification")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="dataset_classification_links", to=settings.AUTH_USER_MODEL)),
                ("dataset", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="classifications", to="imagery.imagerydataset")),
            ],
        ),
        migrations.CreateModel(
            name="DatasetTag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="dataset_tag_links", to=settings.AUTH_USER_MODEL)),
                ("dataset", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="catalog_tags", to="imagery.imagerydataset")),
                ("tag", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="dataset_links", to="catalog_governance.tag")),
            ],
        ),
        migrations.CreateModel(
            name="ImageryClassification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("source", models.CharField(choices=[("manual", "Manual"), ("rule", "Rule"), ("parser", "Parser")], default="manual", max_length=20)),
                ("confidence", models.FloatField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("classification", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="imagery_links", to="catalog_governance.classification")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="imagery_classification_links", to=settings.AUTH_USER_MODEL)),
                ("imagery", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="classifications", to="imagery.imageryrecord")),
            ],
        ),
        migrations.CreateModel(
            name="ImageryTag",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="imagery_tag_links", to=settings.AUTH_USER_MODEL)),
                ("imagery", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="catalog_tags", to="imagery.imageryrecord")),
                ("tag", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="imagery_links", to="catalog_governance.tag")),
            ],
        ),
        migrations.AddConstraint(model_name="administrativeunit", constraint=models.UniqueConstraint(fields=("level", "code", "source_version"), name="unique_admin_unit_version_code")),
        migrations.AddConstraint(model_name="classification", constraint=models.UniqueConstraint(fields=("parent", "name"), name="unique_classification_sibling_name")),
        migrations.AddConstraint(model_name="imageryadministrativeunit", constraint=models.UniqueConstraint(fields=("imagery", "administrative_unit"), name="unique_imagery_admin_unit")),
        migrations.AddConstraint(model_name="datasetclassification", constraint=models.UniqueConstraint(fields=("dataset", "classification"), name="unique_dataset_classification")),
        migrations.AddConstraint(model_name="datasettag", constraint=models.UniqueConstraint(fields=("dataset", "tag"), name="unique_dataset_tag")),
        migrations.AddConstraint(model_name="imageryclassification", constraint=models.UniqueConstraint(fields=("imagery", "classification"), name="unique_imagery_classification")),
        migrations.AddConstraint(model_name="imagerytag", constraint=models.UniqueConstraint(fields=("imagery", "tag"), name="unique_imagery_tag")),
    ]
