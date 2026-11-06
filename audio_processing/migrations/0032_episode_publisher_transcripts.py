from django.db import migrations, models
from django.utils import timezone

TASK_NAME = "find publisher transcripts"
TASK = "audio_processing.tasks.episode_tasks.find_publisher_transcripts_task"


def schedule_hourly(apps, schema_editor):
    """Look for publisher transcripts every hour."""
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTasks = apps.get_model("django_celery_beat", "PeriodicTasks")

    interval = IntervalSchedule.objects.filter(every=1, period="hours").first()
    if interval is None:
        interval = IntervalSchedule.objects.create(every=1, period="hours")
    PeriodicTask.objects.update_or_create(
        name=TASK_NAME,
        defaults={
            "task": TASK,
            "interval": interval,
            "crontab": None,
            "enabled": True,
        },
    )
    # Tell a running beat its schedule changed (save signals don't fire here).
    PeriodicTasks.objects.update_or_create(
        ident=1, defaults={"last_update": timezone.now()}
    )


def unschedule(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(
        name=TASK_NAME
    ).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("audio_processing", "0031_processingbatch_episode_ids"),
        ("django_celery_beat", "__latest__"),
    ]

    operations = [
        migrations.AddField(
            model_name="episode",
            name="transcript_links",
            field=models.JSONField(
                blank=True,
                default=list,
                help_text="Transcripts the feed publishes for this episode: [{url, type}]",
            ),
        ),
        migrations.AddField(
            model_name="episode",
            name="transcript_source",
            field=models.CharField(
                blank=True,
                default="",
                help_text='Where the transcript came from, e.g. "publisher:json"; '
                "blank for our own speech-to-text",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="episode",
            name="publisher_transcript_checked_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the feed's transcript links were last found unusable",
                null=True,
            ),
        ),
        migrations.RunPython(schedule_hourly, unschedule),
    ]
