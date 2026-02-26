from django.contrib import admin
from import_export.admin import ImportExportModelAdmin

from audio_processing.models import Podcast
from audio_processing.tasks.podcast_tasks import (
    index_podcast_for_search,
    process_podcast_by_id,
    reindex_all_podcasts_for_search,
)


@admin.register(Podcast)
class PodcastAdmin(ImportExportModelAdmin):
    list_display = ('name', 'slug', 'author', 'language', 'is_active', 'last_processed', 'episode_count')
    list_filter = ('is_active', 'language', 'itunes_type', 'created_at', 'last_processed', 'tags')
    search_fields = ('name', 'slug', 'url', 'description', 'author', 'subtitle')
    readonly_fields = ('created_at', 'updated_at', 'last_processed', 'pub_date', 'last_build_date')
    list_editable = ('is_active',)

    def episode_count(self, obj):
        return obj.episodes.count()
    episode_count.short_description = 'Episode Count'

    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'url', 'description', 'is_active', 'tags')
        }),
        ('Podcast Metadata', {
            'fields': ('subtitle', 'summary', 'author', 'language', 'copyright'),
            'classes': ('collapse',)
        }),
        ('iTunes Information', {
            'fields': ('itunes_explicit', 'itunes_type', 'itunes_categories'),
            'classes': ('collapse',)
        }),
        ('Images & Branding', {
            'fields': ('image_url', 'itunes_image_url'),
            'classes': ('collapse',)
        }),
        ('Owner Information', {
            'fields': ('owner_name', 'owner_email'),
            'classes': ('collapse',)
        }),
        ('Publication Dates', {
            'fields': ('pub_date', 'last_build_date', 'last_processed'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    actions = ['mark_active', 'mark_inactive', 'process_feed', 'index_to_search', 'reindex_to_search']

    def mark_active(self, request, queryset):
        queryset.update(is_active=True)
        self.message_user(request, f"{queryset.count()} Podcasts marked as active.")
    mark_active.short_description = "Mark selected Podcasts as active"

    def mark_inactive(self, request, queryset):
        queryset.update(is_active=False)
        self.message_user(request, f"{queryset.count()} Podcasts marked as inactive.")
    mark_inactive.short_description = "Mark selected Podcasts as inactive"

    def process_feed(self, request, queryset):
        for podcast in queryset:
            process_podcast_by_id.delay(podcast.id)
        self.message_user(request, f"Processing initiated for {queryset.count()} Podcasts.")
    process_feed.short_description = "Process selected Podcasts"

    def index_to_search(self, request, queryset):
        for podcast in queryset:
            try:
                index_podcast_for_search.delay(podcast.id)
            except Exception as e:
                self.message_user(request, f"Error indexing podcast '{podcast.name}': {str(e)}", level='ERROR')
        self.message_user(request, f"Indexing initiated for {queryset.count()} podcasts.")

    def reindex_to_search(self, request, queryset):
        reindex_all_podcasts_for_search.delay()
        self.message_user(request, "Reindexing of all podcasts has been initiated.")
