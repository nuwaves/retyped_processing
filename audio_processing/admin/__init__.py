"""Admin package initializer: import submodules so Django registers admin classes."""

from django.contrib import admin

from audio_processing.models import Bookmark, ContentRequest, Follow

from . import (
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


@admin.register(ContentRequest)
class ContentRequestAdmin(admin.ModelAdmin):
    list_display = ("episode", "user", "created_at")
    list_select_related = ("episode", "user")
    search_fields = ("episode__title", "user__email", "user__username")
    raw_id_fields = ("episode", "user")
    date_hierarchy = "created_at"
