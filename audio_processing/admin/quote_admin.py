from django.contrib import admin

from audio_processing.models import Quote


@admin.register(Quote)
class QuoteAdmin(admin.ModelAdmin):
    list_display = ('speaker', 'created_at')
    list_filter = ('created_at', 'episode__podcast')
    search_fields = ('text', 'speaker', 'episode__title', 'episode__podcast__name')
    readonly_fields = ('created_at', 'updated_at')
    raw_id_fields = ('episode',)
    date_hierarchy = 'created_at'
    fieldsets = (
        ('Quote Content', {
            'fields': ('episode', 'text', 'speaker')
        }),
        ('Metadata', {
            'fields': ('timestamp',)
        }),
        ('System Info', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
