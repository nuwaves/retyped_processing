from celery import Celery
from django.conf import settings

celery = Celery("tasks", broker=settings.CELERY_BROKER_URL)
celery.conf.broker_transport_options = {
    "queue_name_prefix": settings.CELERY_QUEUE_NAME_PREFIX
}
