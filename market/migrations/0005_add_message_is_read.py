"""Add is_read field to Message model.

Generated migration so you don't need to run makemigrations on Render.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('market', '0004_add_archived_field'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='is_read',
            field=models.BooleanField(default=False),
        ),
    ]
