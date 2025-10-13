from django.contrib import admin
from audio_processing.models import Entity
from audio_processing.tasks.entity_tasks import index_entity_for_search, reindex_all_entities_for_search


@admin.register(Entity)
class EntityAdmin(admin.ModelAdmin):
    list_display = ('name', 'type', 'created_at', 'updated_at')
    list_filter = ('type', 'created_at', 'updated_at')
    search_fields = ('name',)
    readonly_fields = ('created_at', 'updated_at')
    fieldsets = (
        ('Entity Information', {
            'fields': ('name', 'type')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    actions = ['index_to_search', 'reindex_to_search']

    def index_to_search(self, request, queryset):
        success_count = 0
        error_count = 0
        for entity in queryset:
            try:
                index_entity_for_search.delay(entity.id)
                success_count += 1
            except Exception as e:
                error_count += 1
                self.message_user(request, f"Error indexing entity '{entity.name}': {str(e)}", level='ERROR')
        if success_count > 0:
            self.message_user(request, f"Successfully indexed {success_count} entity(ies) to Meilisearch.")
        if error_count > 0:
            self.message_user(request, f"{error_count} entity(ies) failed to index.", level='ERROR')

    def reindex_to_search(self, request, queryset):
        reindex_all_entities_for_search.delay()
        self.message_user(request, "Reindexing of all entities has been initiated.")
