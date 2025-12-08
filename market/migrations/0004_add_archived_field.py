"""Add archived field to Product model.

Generated migration so you don't need to run makemigrations on Render.
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('market', '0003_product_has_variants_product_stock_productvariant_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='product',
            name='archived',
            field=models.BooleanField(default=False),
        ),
    ]
