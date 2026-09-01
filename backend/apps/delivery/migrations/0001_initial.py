from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):
    initial = True
    dependencies = [("imagery", "0003_imageryrecord_archived_at_imageryrecord_archived_by_and_more")]
    operations = [
        migrations.CreateModel(name="DeliveryBasket", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ("created_at", models.DateTimeField(auto_now_add=True)), ("updated_at", models.DateTimeField(auto_now=True)),
            ("owner", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="delivery_basket", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="ExportJob", fields=[
            ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
            ("format", models.CharField(choices=[("manifest", "Manifest"), ("stac", "STAC"), ("zip", "ZIP")], max_length=20)),
            ("status", models.CharField(choices=[("pending", "Pending"), ("running", "Running"), ("done", "Done"), ("failed", "Failed")], db_index=True, default="pending", max_length=20)),
            ("imagery_ids", models.JSONField(default=list)), ("file_path", models.TextField(blank=True)), ("file_size", models.BigIntegerField(blank=True, null=True)),
            ("error", models.TextField(blank=True)), ("expires_at", models.DateTimeField(blank=True, null=True)), ("created_at", models.DateTimeField(auto_now_add=True)),
            ("started_at", models.DateTimeField(blank=True, null=True)), ("finished_at", models.DateTimeField(blank=True, null=True)),
            ("owner", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="export_jobs", to=settings.AUTH_USER_MODEL)),
        ]),
        migrations.CreateModel(name="DeliveryBasketItem", fields=[
            ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")), ("added_at", models.DateTimeField(auto_now_add=True)),
            ("basket", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="delivery.deliverybasket")),
            ("imagery", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="delivery_items", to="imagery.imageryrecord")),
        ]),
        migrations.AddConstraint(model_name="deliverybasketitem", constraint=models.UniqueConstraint(fields=("basket", "imagery"), name="unique_delivery_basket_imagery")),
    ]
