from django.contrib import admin

from audio_processing.models import PodcastOwner


@admin.register(PodcastOwner)
class PodcastOwnerAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'podcast_name', 'approval_status', 'date_approved', 'date_rejected', 'created_at')
    list_filter = ('approval_status', 'created_at', 'date_approved', 'date_rejected')
    search_fields = ('first_name', 'last_name', 'email', 'podcast__name')
    readonly_fields = ('created_at', 'updated_at', 'date_approved', 'date_rejected')
    raw_id_fields = ('podcast', 'approved_by')
    list_editable = ('approval_status',)

    def podcast_name(self, obj):
        return obj.podcast.name if obj.podcast else '-'
    podcast_name.short_description = 'Podcast'
    podcast_name.admin_order_field = 'podcast__name'

    def full_name(self, obj):
        return obj.full_name
    full_name.short_description = 'Full Name'
    full_name.admin_order_field = 'first_name'
