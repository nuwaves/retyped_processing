from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('audio_processing', '0010_episode_slug'),
    ]

    operations = [
        migrations.AlterField(
            model_name='podcast',
            name='slug',
            field=models.SlugField(blank=True, help_text='Unique slug for podcast', max_length=255, unique=True),
        ),
        migrations.AlterField(
            model_name='episode',
            name='slug',
            field=models.SlugField(blank=True, help_text='Unique slug for episode, prefixed with podcast slug', max_length=512, unique=True),
        ),
    ]
