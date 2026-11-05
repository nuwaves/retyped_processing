from django.db import migrations, models
from django.utils import timezone

BATCH_TASK_NAME = "fetch groq batches"
BATCH_TASK = "audio_processing.tasks.batch_tasks.process_pending_batches_task"


def run_batches_every_15_minutes(apps, schema_editor):
    """
    Transcription now defaults to Groq batch jobs, and this task both submits
    them and collects their results, so it has to run often (it ran every 12h).
    """
    IntervalSchedule = apps.get_model("django_celery_beat", "IntervalSchedule")
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTasks = apps.get_model("django_celery_beat", "PeriodicTasks")

    interval = IntervalSchedule.objects.filter(every=15, period="minutes").first()
    if interval is None:
        interval = IntervalSchedule.objects.create(every=15, period="minutes")
    PeriodicTask.objects.update_or_create(
        name=BATCH_TASK_NAME,
        defaults={
            "task": BATCH_TASK,
            "interval": interval,
            "crontab": None,
            "enabled": True,
        },
    )
    # Tell a running beat its schedule changed (save signals don't fire here).
    PeriodicTasks.objects.update_or_create(
        ident=1, defaults={"last_update": timezone.now()}
    )


class Migration(migrations.Migration):
    dependencies = [
        ("audio_processing", "0030_episode_processing_status_podcast_auto_process"),
        ("django_celery_beat", "__latest__"),
    ]

    operations = [
        migrations.AddField(
            model_name="processingbatch",
            name="episode_ids",
            field=models.JSONField(
                blank=True, default=list, help_text="Episodes transcribed by this batch"
            ),
        ),
        migrations.RunPython(run_batches_every_15_minutes, migrations.RunPython.noop),
    ]
