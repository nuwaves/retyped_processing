"""
Development settings for audio_processing project.
"""

from dotenv import load_dotenv

from .base import *

# Load environment variables
load_dotenv(BASE_DIR / ".env.dev")

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = "django-insecure-5wh5q4v%ak6cyobga4x#ngitaft8w-w_hit*94(#_6+r*auzs*"

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "*",
]

# Development-specific database settings (if needed)
# DATABASES['default']['OPTIONS'] = {
#     'init_command': "SET sql_mode='STRICT_TRANS_TABLES'"
# }

# Development logging - more verbose
LOGGING["handlers"]["console"]["level"] = "DEBUG"
LOGGING["loggers"]["django"]["level"] = "INFO"
LOGGING["loggers"]["audio_processing"]["level"] = "DEBUG"

# Development-specific Meilisearch (local instance)
if not MEILISEARCH_URL:
    MEILISEARCH_URL = "http://localhost:7700"

# Email backend for development (console)
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Additional development apps
INSTALLED_APPS += [
    # Add development-only apps here if needed
    # 'debug_toolbar',
]

# Development-specific middleware
# MIDDLEWARE += [
#     'debug_toolbar.middleware.DebugToolbarMiddleware',
# ]

# Internal IPs for debug toolbar
# INTERNAL_IPS = [
#     '127.0.0.1',
# ]

CELERY_QUEUE_NAME_PREFIX = "dev-"
