# Generated by Django 4.2.21 on 2025-06-13 10:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('directories', '0025_directorypricing_include_tax_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='directorypricing',
            name='label',
            field=models.CharField(default='', blank=True, max_length=100),
        ),
    ]
