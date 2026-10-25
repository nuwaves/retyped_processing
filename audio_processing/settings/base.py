"""
Base Django settings for audio_processing project.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Application definition
INSTALLED_APPS = [
    "constance",
    # 'admin_tools_stats',
    "django_nvd3",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "audio_processing",
    "import_export",
    "corsheaders",
    "rest_framework",
    "drf_yasg",
    "oauth2_provider",
    "social_django",
    "drf_social_oauth2",
    "django_celery_beat",
    "django.contrib.sites",
    "django.contrib.sitemaps",
]

SITE_ID = 1

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "audio_processing.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "social_django.context_processors.backends",
                "social_django.context_processors.login_redirect",
            ],
        },
    },
]

WSGI_APPLICATION = "audio_processing.wsgi.application"

# Database
# https://docs.djangoproject.com/en/5.2/ref/settings/#databases
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("DB_NAME", "audio_processing"),
        "USER": os.environ.get("DB_USER", "postgres"),
        "PASSWORD": os.environ.get("DB_PASSWORD", ""),
        "HOST": os.environ.get("DB_HOST", "localhost"),
        "PORT": os.environ.get("DB_PORT", "5432"),
    }
}

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]

# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Email settings
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "noreply@retyped.com")
SERVER_EMAIL = os.environ.get("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

# Verification settings
VERIFICATION_EXPIRY_HOURS = int(os.environ.get("VERIFICATION_EXPIRY_HOURS", "48"))

# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/
STATIC_URL = "static/"

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# API Keys
WHISPER_API_KEY = os.environ.get("WHISPER_API_KEY", "")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

# AWS settings
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
AWS_S3_BUCKET = os.environ.get("AWS_S3_BUCKET", None)
AWS_TRANSCRIBE_OUTPUT_BUCKET = os.environ.get("AWS_TRANSCRIBE_OUTPUT_BUCKET", None)
# Set to an S3-compatible endpoint (e.g. Cloudflare R2) to store audio outside AWS.
AWS_S3_ENDPOINT_URL = os.environ.get("AWS_S3_ENDPOINT_URL") or None
# Public base URL that serves objects from AWS_S3_BUCKET.
AUDIO_CDN_URL = os.environ.get("AUDIO_CDN_URL", "https://cdn.retyped.xyz").rstrip("/")

# Timeout in seconds for outbound HTTP calls (Groq, feeds, audio downloads).
HTTP_TIMEOUT = int(os.environ.get("HTTP_TIMEOUT", "120"))

# OpenAI-compatible chat completions endpoint for the LLM steps (tags, entities,
# quotes, summaries, speaker scripts, topics). Whisper transcription stays on Groq.
LLM_API_URL = os.environ.get(
    "LLM_API_URL", "https://api.deepinfra.com/v1/openai/chat/completions"
)
LLM_API_KEY = os.environ.get("LLM_API_KEY", "")
# Speaker scripts take several minutes to generate, well past HTTP_TIMEOUT.
LLM_TIMEOUT = int(os.environ.get("LLM_TIMEOUT", "600"))

# Redis serves as the Celery broker and the shared Django cache when REDIS_URL is set.
REDIS_URL = os.environ.get("REDIS_URL", "")

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
            "KEY_PREFIX": "audio_processing",
        }
    }

# Celery settings
CELERY_BROKER_URL = os.environ.get(
    "CELERY_BROKER_URL", f"sqs://{AWS_ACCESS_KEY_ID}:{AWS_SECRET_ACCESS_KEY}@"
)
CELERY_QUEUE_NAME_PREFIX = ""

# Stop runaway tasks: the soft limit raises SoftTimeLimitExceeded so the task can
# record the failure, and the hard limit kills the worker process.
CELERY_TASK_SOFT_TIME_LIMIT = int(os.environ.get("CELERY_TASK_SOFT_TIME_LIMIT", "5400"))
CELERY_TASK_TIME_LIMIT = int(os.environ.get("CELERY_TASK_TIME_LIMIT", "6000"))

if CELERY_BROKER_URL.startswith("redis"):
    # Redis redelivers unacknowledged tasks after visibility_timeout (default 1 hour),
    # so it must outlast the longest task or long episodes get processed twice.
    CELERY_BROKER_TRANSPORT_OPTIONS = {
        "visibility_timeout": CELERY_TASK_TIME_LIMIT + 600
    }

# Meilisearch settings
MEILISEARCH_URL = os.environ.get("MEILISEARCH_URL", "")
MEILISEARCH_API_KEY = os.environ.get("MEILISEARCH_API_KEY", "")

# Constance settings
CHAT_MODEL = "deepseek-ai/DeepSeek-V4-Flash"
CONSTANCE_CONFIG = {
    "DEFAULT_MODEL": (CHAT_MODEL, "Model for tags, entities and quotes"),
    "SUMMARY_MODEL": (CHAT_MODEL, "Model to use for generating summaries"),
    "TAG_MODEL": (CHAT_MODEL, "Model to use for picking topics"),
    "SPEAKER_MODEL": (CHAT_MODEL, "Model to use for speaker diarization"),
    "TEXT_TO_SPEECH_MODEL": (
        "whisper-large-v3-turbo",
        "Model to use for text-to-speech synthesis",
    ),
}
CONSTANCE_BACKEND = "constance.backends.database.DatabaseBackend"

# Logging configuration
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {process:d} {thread:d} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "level": LOG_LEVEL,
        },
        "file": {
            "class": "logging.FileHandler",
            "filename": "django.log",
            "formatter": "verbose",
            "level": LOG_LEVEL,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
        "audio_processing": {
            "handlers": ["console"],
            "level": LOG_LEVEL,
            "propagate": False,
        },
    },
}

# REST Framework configuration

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.LimitOffsetPagination",
    "PAGE_SIZE": 32,
    # The first class sets the WWW-Authenticate header on 401s. OAuth2 goes first
    # so unauthenticated requests get 401 (the frontend proxy relies on it), not 403.
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "oauth2_provider.contrib.rest_framework.OAuth2Authentication",
        "drf_social_oauth2.authentication.SocialAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
}

# Social Auth configuration

SOCIAL_AUTH_JSONFIELD_ENABLED = True

# Google configuration
SOCIAL_AUTH_GOOGLE_OAUTH2_KEY = os.environ.get("SA_GOOGLE_OAUTH2_KEY", "")
SOCIAL_AUTH_GOOGLE_OAUTH2_SECRET = os.environ.get("SA_GOOGLE_OAUTH2_SECRET", "")

# Define SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE to get extra permissions from Google.
SOCIAL_AUTH_GOOGLE_OAUTH2_SCOPE = [
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
]

# Facebook configuration
SOCIAL_AUTH_FACEBOOK_KEY = os.environ.get("SA_FACEBOOK_LOGIN_KEY", "")
SOCIAL_AUTH_FACEBOOK_SECRET = os.environ.get("SA_FACEBOOK_LOGIN_SECRET", "")

# Define SOCIAL_AUTH_FACEBOOK_SCOPE to get extra permissions from Facebook.
# Email is not sent by default, to get it, you must request the email permission.
SOCIAL_AUTH_FACEBOOK_SCOPE = ["email"]
# SOCIAL_AUTH_FACEBOOK_PROFILE_EXTRA_PARAMS = {}

# Twitter configuration
SOCIAL_AUTH_TWITTER_KEY = os.environ.get("SA_TWITTER_API_KEY", "")
SOCIAL_AUTH_TWITTER_SECRET = os.environ.get("SA_TWITTER_API_SECRET", "")

# Instagram Configuration
# Instagram configuration
SOCIAL_AUTH_INSTAGRAM_KEY = os.environ.get("SA_INSTAGRAM_AUTH_KEY", "")
SOCIAL_AUTH_INSTAGRAM_SECRET = os.environ.get("SA_INSTAGRAM_AUTH_SECRET", "")
# SOCIAL_AUTH_INSTAGRAM_AUTH_EXTRA_ARGUMENTS = {'scope': 'likes comments relationships'}

# CORS Configuration
if os.environ.get("CORS_ALLOWED_ORIGINS", None):
    CORS_ALLOWED_ORIGINS = os.environ.get("CORS_ALLOWED_ORIGINS").split(",")

AUTHENTICATION_BACKENDS = (
    "social_core.backends.google.GoogleOAuth2",
    "social_core.backends.instagram.InstagramOAuth2",
    "social_core.backends.facebook.FacebookAppOAuth2",
    "social_core.backends.facebook.FacebookOAuth2",
    "social_core.backends.twitter.TwitterOAuth",
    "drf_social_oauth2.backends.DjangoOAuth2",
    "django.contrib.auth.backends.ModelBackend",
)
