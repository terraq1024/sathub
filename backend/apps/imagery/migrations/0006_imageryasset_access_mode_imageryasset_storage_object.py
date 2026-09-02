from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('imagery', '0005_imageryrecord_cog_error_imageryrecord_cog_path_and_more'),
        ('storage_manager', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='imageryasset',
            name='access_mode',
            field=models.CharField(choices=[('reference', 'Reference'), ('managed', 'Managed'), ('derived', 'Derived')], default='managed', max_length=20),
        ),
        migrations.AddField(
            model_name='imageryasset',
            name='storage_object',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='imagery_assets', to='storage_manager.storageobject'),
        ),
    ]
