from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from audio_processing.models import Tag


@admin.register(Tag)
class TagAdmin(ImportExportModelAdmin):
    list_display = (
        "name",
        "slug",
        "color_display",
        "podcast_count",
        "podcast_count",
        "created_at",
    )
    list_filter = ("created_at", "updated_at")
    search_fields = ("name", "slug", "description")
    readonly_fields = ("created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}

    def color_display(self, obj):
        if obj.color:
            return f'<span style="background-color: {obj.color}; padding: 3px 8px; border-radius: 3px; color: white;">{obj.color}</span>'
        return "-"

    color_display.allow_tags = True
    color_display.short_description = "Color"

    def episode_count(self, obj):
        return obj.episodes.count()

    episode_count.short_description = "Episodes"

    def podcast_count(self, obj):
        return obj.podcasts.count()

    podcast_count.short_description = "Podcasts"
