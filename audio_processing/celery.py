import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "audio_processing.settings")

app = Celery("audio_processing")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.on_after_configure.connect
def setup_periodic_tasks(sender: Celery, **kwargs):
    from audio_processing.tasks.episode_tasks import backfill_topics_for_recent_episodes
    from audio_processing.tasks.podcast_tasks import (
        import_top_chart_podcasts,
        process_all_active_podcasts,
    )

    sender.add_periodic_task(
        60 * 60 * 24,
        process_all_active_podcasts.s(),
        name="process all active podcasts",
    )

    sender.add_periodic_task(
        60 * 60 * 6,  # every 6 hours
        backfill_topics_for_recent_episodes.s(),
        name="backfill topics for recent episodes",
    )

    sender.add_periodic_task(
        crontab(hour=5, minute=0, day_of_week="mon"),
        import_top_chart_podcasts.s(),
        name="import top chart podcasts",
    )
