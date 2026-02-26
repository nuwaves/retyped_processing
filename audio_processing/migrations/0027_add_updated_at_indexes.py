# Generated migration to add indexes for faster sitemap sorting

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('audio_processing', '0026_podcastclaim_claimverification'),
    ]

    operations = [
        migrations.AlterField(
            model_name='episode',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
        migrations.AlterField(
            model_name='podcast',
            name='updated_at',
            field=models.DateTimeField(auto_now=True, db_index=True),
        ),
    ]
