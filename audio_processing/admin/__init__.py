"""Admin package initializer: import submodules so Django registers admin classes."""
from . import processing_batch_admin  # noqa: F401
from . import user_analytics_admin  # noqa: F401
from . import entity_admin  # noqa: F401
from . import podcast_admin  # noqa: F401
from . import episode_admin  # noqa: F401
from . import tag_admin  # noqa: F401
from . import podcast_owner_admin  # noqa: F401
from . import quote_admin  # noqa: F401
from . import topic_admin  # noqa: F401

from django.contrib import admin
from audio_processing.models import Follow, Bookmark

admin.site.register(Follow)
admin.site.register(Bookmark)
