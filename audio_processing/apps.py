"""
Django app configuration for audio_processing.

This module defines the app configuration and ensures that
signals are registered when the app is ready.
"""
from django.apps import AppConfig


class AudioProcessingConfig(AppConfig):
    """
    Configuration for the audio_processing Django app.
    """
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'audio_processing'
    verbose_name = 'Audio Processing'

    def ready(self):
        """
        Import signal handlers when the app is ready.

        This method is called once Django has fully loaded the app,
        ensuring that signal handlers are registered and ready to process events.
        """
        # Import signals to register them
        import audio_processing.signals  # noqa: F401
