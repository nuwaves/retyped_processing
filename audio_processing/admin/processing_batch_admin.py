from django.contrib import admin
from audio_processing.models.processing_batch import ProcessingBatch
from audio_processing.tasks.batch_tasks import fetch_and_apply_groq_results_task


@admin.register(ProcessingBatch)
class ProcessingBatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'external_batch_id', 'processing_state', 'record_count', 'created_at', 'updated_at')
    list_filter = ('processing_state', 'created_at', 'updated_at')
    search_fields = ('external_batch_id',)
    readonly_fields = ('created_at', 'updated_at', 'external_batch_id', 'record_count', 'processing_state', 'error')
    fieldsets = (
        (None, {
            'fields': ('external_batch_id', 'processing_state', 'record_count', 'error')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    actions = ['fetch_and_apply_groq_results_action']

    def fetch_and_apply_groq_results_action(self, request, queryset):
        for batch in queryset:
            async_result = fetch_and_apply_groq_results_task.delay(batch.id)
            self.message_user(request, f"Batch {batch.id}: Task queued (Celery ID: {async_result.id})")
    fetch_and_apply_groq_results_action.short_description = "Fetch/apply Groq results for selected batches (async)"
