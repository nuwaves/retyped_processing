import os
from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "audio_processing.settings")

app = Celery("audio_processing")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.on_after_configure.connect
def setup_periodic_tasks(sender: Celery, **kwargs):
    from audio_processing.tasks.podcast_tasks import process_all_active_podcasts
    sender.add_periodic_task(60 * 60 * 24, process_all_active_podcasts.s(), name='process all active podcasts')
    from audio_processing.tasks.core_tasks import notify_google_of_new_sitemap
    sender.add_periodic_task(60 * 60 * 24, notify_google_of_new_sitemap.s(), name='notify google of new sitemap daily')