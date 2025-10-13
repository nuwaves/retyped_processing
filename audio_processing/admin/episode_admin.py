from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from audio_processing.models import Episode
from audio_processing.tasks.episode_tasks import add_transcript, suggest_and_apply_tags, process_complete_workflow, extract_quotes, index_episode_for_search, reindex_all_episodes_for_search, save_audio_to_s3_task, tag_episode_with_topics
from audio_processing.tasks.episode_tasks import groq_batch_transcribe, extract_entities
from audio_processing.tasks.episode_tasks import suggest_and_apply_tags as suggest_and_apply_tags_task
from audio_processing.tasks.episode_tasks import extract_quotes as extract_quotes_task
from audio_processing.tasks.episode_tasks import add_transcript as add_transcript_task


class ProcessingCompletedFilter(SimpleListFilter):
    title = 'Processing Completed'
    parameter_name = 'processing_completed_at'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Yes'),
            ('no', 'No'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.exclude(processing_completed_at__isnull=True)
        if self.value() == 'no':
            return queryset.filter(processing_completed_at__isnull=True)
        return queryset


class HasErrorFilter(SimpleListFilter):
    title = 'Has Error'
    parameter_name = 'has_error'

    def lookups(self, request, model_admin):
        return (
            ('yes', 'Yes'),
            ('no', 'No'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'yes':
            return queryset.exclude(error__isnull=True).exclude(error='')
        if self.value() == 'no':
            return queryset.filter(models.Q(error__isnull=True) | models.Q(error=''))
        return queryset


@admin.register(Episode)
class EpisodeAdmin(admin.ModelAdmin):
    list_display = ('title', 'slug', 'podcast', 'duration_display', 'has_transcript', 'has_script', 'has_summary', 'release_date', 'error')

    class HasTranscriptFilter(SimpleListFilter):
        title = 'Has Transcript'
        parameter_name = 'has_transcript'

        def lookups(self, request, model_admin):
            return (
                ('yes', 'Yes'),
                ('no', 'No'),
            )

        def queryset(self, request, queryset):
            if self.value() == 'yes':
                return queryset.exclude(transcript__isnull=True).exclude(transcript='')
            if self.value() == 'no':
                return queryset.filter(models.Q(transcript__isnull=True) | models.Q(transcript=''))
            return queryset

    list_filter = ('podcast', 'episode_type', 'itunes_explicit', 'created_at', 'updated_at', 'tags', 'release_date', ProcessingCompletedFilter, HasTranscriptFilter, HasErrorFilter)
    search_fields = ('title', 'slug', 'description', 'raw_audio_url', 'transcript', 'script_transcript', 'podcast__name')
    readonly_fields = ('created_at', 'updated_at', 'audio_length', 'pub_date', 'error')
    raw_id_fields = ('podcast',)

    def truncated_url(self, obj):
        if len(obj.raw_audio_url) > 50:
            return obj.raw_audio_url[:47] + "..."
        return obj.raw_audio_url
    truncated_url.short_description = 'Audio URL'
    
    def duration_display(self, obj):
        if obj.duration:
            total_seconds = int(obj.duration.total_seconds())
            hours, remainder = divmod(total_seconds, 3600)
            minutes, seconds = divmod(remainder, 60)
            if hours:
                return f"{hours}:{minutes:02d}:{seconds:02d}"
            else:
                return f"{minutes}:{seconds:02d}"
        return '-'
    duration_display.short_description = 'Duration'
    
    def has_transcript(self, obj):
        return bool(obj.transcript and obj.transcript.strip())
    has_transcript.boolean = True
    has_transcript.short_description = 'Has Transcript'
    
    def has_script(self, obj):
        return bool(obj.script_transcript and obj.script_transcript.strip())
    has_script.boolean = True
    has_script.short_description = 'Has Script'

    def has_summary(self, obj):
        return bool(obj.summary and obj.summary.strip())
    has_summary.boolean = True
    has_summary.short_description = 'Has Summary'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('podcast', 'title', 'slug', 'subtitle',
                       'description', 'tags', 'topics')
        }),
        ('Audio Information', {
            'fields': ('raw_audio_url', 's3_audio_url', 'audio_type', 'audio_length', 'duration'),
            'classes': ('collapse',)
        }),
        ('Episode Metadata', {
            'fields': ('episode_number', 'season_number', 'episode_type'),
            'classes': ('collapse',)
        }),
        ('iTunes Information', {
            'fields': ('itunes_explicit', 'itunes_episode_type'),
            'classes': ('collapse',)
        }),
        ('Rich Content', {
            'fields': ('content_encoded',),
            'classes': ('collapse',)
        }),
        ('Processing Content', {
            'fields': ('transcript', 'script_transcript', 'summary', 'processing_completed_at'),
            'classes': ('wide',)
        }),
        ('Dates', {
            'fields': ('release_date', 'pub_date'),
            'classes': ('collapse',)
        }),
        ('System Information', {
            'fields': ('error', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )

    actions = ['clear_transcript', 'export_transcripts', 'fetch_transcript',
               'generate_speaker_scripts', 'run_complete_workflow', 'add_summary',
               'extract_quotes_action', 'index_to_search', 'extract_entities_action', 'batch_groq_transcribe',
               'reindex_to_search', 'save_audio_to_s3_action', 'tag_episode_with_topics']

    def tag_episode_with_topics(self, request, queryset):
        from audio_processing.tasks.episode_tasks import tag_episode_with_topics
        success_count = 0
        error_count = 0
        no_transcript_count = 0
        for episode in queryset:
            if not episode.transcript or not episode.transcript.strip():
                no_transcript_count += 1
                continue
            try:
                tag_episode_with_topics.delay(episode.id)
                success_count += 1
            except Exception as e:
                error_count += 1
                self.message_user(
                    request,
                    f"Error tagging topics for {episode.title or 'Untitled'}: {str(e)}",
                    level='ERROR'
                )
        if success_count > 0:
            self.message_user(
                request,
                f"Topic tagging initiated for {success_count} episode(s)."
            )
        if no_transcript_count > 0:
            self.message_user(
                request,
                f"{no_transcript_count} episode(s) skipped due to missing transcripts.",
                level='WARNING'
            )
        if error_count > 0:
            self.message_user(
                request,
                f"Errors occurred for {error_count} episode(s).",
                level='ERROR'
            )
    tag_episode_with_topics.short_description = "Tag selected episodes with topics (async)"

    def save_audio_to_s3_action(self, request, queryset):
        success_count = 0
        error_count = 0
        for episode in queryset:
            try:
                async_result = save_audio_to_s3_task.delay(episode.id)
                success_count += 1
            except Exception as e:
                error_count += 1
                self.message_user(request, f"Error saving audio to S3 for {episode.title or episode.id}: {str(e)}", level='ERROR')
        if success_count > 0:
            self.message_user(request, f"Queued S3 upload for {success_count} episode(s).")
        if error_count > 0:
            self.message_user(request, f"{error_count} episode(s) failed to queue for S3 upload.", level='ERROR')
    save_audio_to_s3_action.short_description = "Save audio file(s) to S3 (async)"

    def batch_groq_transcribe(self, request, queryset):
        from audio_processing.tasks.episode_tasks import groq_batch_transcribe
        episode_ids = list(queryset.values_list('id', flat=True))
        try:
            async_result = groq_batch_transcribe.delay(episode_ids)
            self.message_user(request, f"Batch transcription task queued. Celery Task ID: {async_result.id}")
        except Exception as e:
            self.message_user(request, f"Batch transcription failed: {str(e)}", level='ERROR')
    batch_groq_transcribe.short_description = "Batch transcribe (Groq) selected episodes (async)"

    def extract_entities_action(self, request, queryset):
        from audio_processing.tasks.episode_tasks import extract_entities
        success_count = 0
        error_count = 0
        no_transcript_count = 0
        for episode in queryset:
            if not episode.transcript or not episode.transcript.strip():
                no_transcript_count += 1
                continue
            try:
                extract_entities.delay(episode.id)
                success_count += 1
            except Exception as e:
                error_count += 1
                self.message_user(
                    request,
                    f"Error extracting entities for {episode.title or 'Untitled'}: {str(e)}",
                    level='ERROR'
                )
        if success_count > 0:
            self.message_user(
                request,
                f"Entity extraction initiated for {success_count} episode(s)."
            )
        if no_transcript_count > 0:
            self.message_user(
                request,
                f"{no_transcript_count} episode(s) skipped (no transcript available).",
                level='WARNING'
            )
        if error_count > 0:
            self.message_user(
                request,
                f"{error_count} episode(s) failed to start entity extraction.",
                level='ERROR'
            )
    extract_entities_action.short_description = "Extract entities from selected episodes"

    def index_to_search(self, request, queryset):
        for episode in queryset:
            try:
                index_episode_for_search.delay(episode.id)
            except Exception as e:
                self.message_user(request, f"Error indexing {episode.raw_audio_url[:50]}...: {str(e)}", level='ERROR')
        self.message_user(request, f"Indexing initiated for {queryset.count()} episodes.")

    def reindex_to_search(self, request, queryset):
        reindex_all_episodes_for_search.delay()
        self.message_user(request, "Reindexing of all episodes has been initiated.")

    def clear_transcript(self, request, queryset):
        queryset.update(transcript='')
        self.message_user(request, f"Cleared transcripts for {queryset.count()} episodes.")
    clear_transcript.short_description = "Clear transcripts for selected episodes"

    def export_transcripts(self, request, queryset):
        count = queryset.filter(transcript__isnull=False).exclude(transcript='').count()
        self.message_user(request, f"Found {count} episodes with transcripts to export.")
    export_transcripts.short_description = "Export transcripts for selected episodes"

    def fetch_transcript(self, request, queryset):
        for episode in queryset:
            add_transcript_task.delay(episode.id)
        self.message_user(request, f"Transcript processing initiated for {queryset.count()} episodes.")
    fetch_transcript.short_description = "Fetch transcripts for selected episodes"

    def add_summary(self, request, queryset):
        success_count = 0
        error_count = 0

        for episode in queryset:
            try:
                summary = episode.generate_summary()
                if summary:
                    success_count += 1
            except Exception as e:
                error_count += 1
                self.message_user(
                    request, 
                    f"Error generating summary for {episode.raw_audio_url[:50]}...: {str(e)}", 
                    level='ERROR'
                )
        
        if success_count > 0:
            self.message_user(
                request, 
                f"Successfully generated summaries for {success_count} podcasts."
            )
        
        if error_count > 0:
            self.message_user(
                request, 
                f"{error_count} podcasts failed to generate summaries.", 
                level='ERROR'
            )

    def generate_speaker_scripts(self, request, queryset):
        success_count = 0
        error_count = 0
        no_transcript_count = 0
        already_has_script_count = 0

        for episode in queryset:
            if not episode.transcript or not episode.transcript.strip():
                no_transcript_count += 1
                continue

            if episode.script_transcript and episode.script_transcript.strip():
                already_has_script_count += 1
                continue
                
            try:
                script = episode.generate_speaker_script()
            except Exception as e:
                error_count += 1
                self.message_user(
                    request, 
                    f"Error generating speaker script for {episode.raw_audio_url[:50]}...: {str(e)}", 
                    level='ERROR'
                )
        
        if success_count > 0:
            self.message_user(
                request, 
                f"Successfully generated speaker scripts for {success_count} podcasts."
            )
        
        if no_transcript_count > 0:
            self.message_user(
                request, 
                f"{no_transcript_count} episodes skipped (no transcript available).", 
                level='WARNING'
            )
        
        if already_has_script_count > 0:
            self.message_user(
                request, 
                f"{already_has_script_count} episodes skipped (already have speaker scripts).", 
                level='WARNING'
            )
        
        if error_count > 0:
            self.message_user(
                request, 
                f"{error_count} episodes failed to generate speaker scripts.", 
                level='ERROR'
            )

    generate_speaker_scripts.short_description = "Generate speaker scripts for selected episodes"

    def run_complete_workflow(self, request, queryset):
        total_processed = 0
        total_errors = []
        
        for episode in queryset:
            try:
                process_complete_workflow.delay(episode.id)
                total_processed += 1
            except Exception as e:
                total_errors.append(f"{episode.raw_audio_url[:30]}...: {str(e)}")
        
        self.message_user(
            request,
            f"Processed {total_processed} episodes. "
        )
        
        if total_errors:
            for error in total_errors[:5]:  # Show first 5 errors
                self.message_user(request, f"Error: {error}", level='ERROR')
            
            if len(total_errors) > 5:
                self.message_user(
                    request, 
                    f"...and {len(total_errors) - 5} more errors. Check logs for details.", 
                    level='ERROR'
                )
    
    run_complete_workflow.short_description = "Run complete workflow (transcript + tags + speaker script)"

    def extract_quotes_action(self, request, queryset):
        success_count = 0
        error_count = 0
        no_transcript_count = 0
        
        for episode in queryset:
            if not episode.transcript or not episode.transcript.strip():
                no_transcript_count += 1
                continue
            
            try:
                extract_quotes_task.delay(episode.id)
                success_count += 1
            except Exception as e:
                error_count += 1
                self.message_user(
                    request, 
                    f"Error initiating quote extraction for {episode.title or 'Untitled'}: {str(e)}", 
                    level='ERROR'
                )
        
        if success_count > 0:
            self.message_user(
                request, 
                f"Quote extraction initiated for {success_count} episode(s)."
            )
        
        if no_transcript_count > 0:
            self.message_user(
                request, 
                f"{no_transcript_count} episode(s) skipped (no transcript available).", 
                level='WARNING'
            )
        
        if error_count > 0:
            self.message_user(
                request, 
                f"{error_count} episode(s) failed to start quote extraction.", 
                level='ERROR'
            )
    
    extract_quotes_action.short_description = "Extract quotes from selected episodes"
