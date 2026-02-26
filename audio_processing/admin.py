
"""Admin package loader: import submodules so Django registers admin classes."""
from django.contrib import admin

from audio_processing.models import Bookmark, Follow

from .admin import (
    entity_admin,  # noqa: F401
    episode_admin,  # noqa: F401
    podcast_admin,  # noqa: F401
    podcast_owner_admin,  # noqa: F401
    processing_batch_admin,  # noqa: F401
    quote_admin,  # noqa: F401
    tag_admin,  # noqa: F401
    topic_admin,  # noqa: F401
    user_analytics_admin,  # noqa: F401
)

admin.site.register(Follow)
admin.site.register(Bookmark)
