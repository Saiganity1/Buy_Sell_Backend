# Generated migration to add archived_at field
from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('market', '0005_add_message_is_read'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='archived_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
