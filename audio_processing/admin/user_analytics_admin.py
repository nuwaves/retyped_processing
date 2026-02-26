from django.contrib import admin

from audio_processing.models.user_analytics import UserAnalytics


@admin.register(UserAnalytics)
class UserAnalyticsAdmin(admin.ModelAdmin):
    list_display = ('user', 'entity_type', 'get_entity_display_name', 'views', 'created_at', 'updated_at')
    list_filter = ('created_at', 'updated_at', 'user')
    search_fields = ('user__username', 'podcast__name', 'episode__title')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('user', 'podcast', 'episode')
    fieldsets = (
        ('User Analytics', {
            'fields': ('user', 'podcast', 'episode', 'views')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
