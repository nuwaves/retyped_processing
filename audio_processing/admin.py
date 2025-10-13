from .models.processing_batch import ProcessingBatch
from .models.user_analytics import UserAnalytics
"""Admin package loader: import submodules so Django registers admin classes."""
from .admin import processing_batch_admin  # noqa: F401
from .admin import user_analytics_admin  # noqa: F401
from .admin import entity_admin  # noqa: F401
from .admin import podcast_admin  # noqa: F401
from .admin import episode_admin  # noqa: F401
from .admin import tag_admin  # noqa: F401
from .admin import podcast_owner_admin  # noqa: F401
from .admin import quote_admin  # noqa: F401
from .admin import topic_admin  # noqa: F401

from django.contrib import admin
from audio_processing.models import Follow, Bookmark

admin.site.register(Follow)
admin.site.register(Bookmark)