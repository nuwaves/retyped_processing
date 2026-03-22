"""
Settings module selector for audio_processing project.

This module automatically imports the appropriate settings based on the DJANGO_SETTINGS_MODULE
environment variable or defaults to development settings.
"""

import os

# Default to development settings if not specified
settings_module = os.environ.get(
    "DJANGO_SETTINGS_MODULE", "audio_processing.settings.dev"
)

if "dev" in settings_module:
    from .dev import *
elif "prod" in settings_module:
    from .prod import *
else:
    # Fallback to dev settings
    from .dev import *
