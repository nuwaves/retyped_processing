"""
Retyped's admin site: stock Django admin plus a processing dashboard and
pages for adding podcasts and managing their episodes.

Installed via RetypedAdminConfig (listed in INSTALLED_APPS in place of
django.contrib.admin), so `admin.site` is this site and the existing
@admin.register calls need no changes.
"""

from django.contrib import admin
from django.contrib.admin.apps import AdminConfig
from django.urls import path


class RetypedAdminConfig(AdminConfig):
    default_site = "audio_processing.admin_site.RetypedAdminSite"


class RetypedAdminSite(admin.AdminSite):
    site_header = "Retyped admin"
    site_title = "Retyped admin"
    index_title = "Dashboard"
    index_template = "retyped_admin/dashboard.html"

    def index(self, request, extra_context=None):
        from audio_processing.admin import dashboard_views

        context = dashboard_views.dashboard_context()
        context.update(extra_context or {})
        return super().index(request, extra_context=context)

    def get_urls(self):
        from audio_processing.admin import dashboard_views as views

        custom = [
            path(
                "podcasts/add-feed/",
                self.admin_view(views.add_feed),
                name="podcast_add_feed",
            ),
            path(
                "podcasts/<int:pk>/episodes/",
                self.admin_view(views.podcast_episodes),
                name="podcast_episodes",
            ),
            path(
                "podcasts/<int:pk>/actions/",
                self.admin_view(views.podcast_action),
                name="podcast_action",
            ),
            path(
                "processing/",
                self.admin_view(views.processing_queue),
                name="processing_queue",
            ),
            path(
                "processing/queue/",
                self.admin_view(views.queue_episodes),
                name="queue_episodes",
            ),
        ]
        # Custom paths first so they win over the model admin catch-alls.
        return custom + super().get_urls()
