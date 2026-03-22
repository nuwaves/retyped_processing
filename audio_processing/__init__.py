from .celery import app as celery_app  # noqa: F401

# Set default app config
default_app_config = "audio_processing.apps.AudioProcessingConfig"
