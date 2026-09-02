from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('imagery', '0005_imageryrecord_cog_error_imageryrecord_cog_path_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='imageryasset',
            name='access_mode',
            field=models.CharField(choices=[('reference', 'Reference'), ('managed', 'Managed'), ('derived', 'Derived')], default='managed', max_length=20),
        ),
    ]
