from .models.processing_batch import ProcessingBatch
from .models.user_analytics import UserAnalytics
from .models import Follow, Bookmark
from django.contrib import admin
from .models import Episode, Podcast, Tag, PodcastOwner, Quote, Entity
from .models import Topic
from django.contrib.admin import SimpleListFilter
from audio_processing.tasks.episode_tasks import add_transcript, suggest_and_apply_tags, process_complete_workflow, extract_quotes, index_episode_for_search, reindex_all_episodes_for_search, save_audio_to_s3_task
from import_export.admin import ImportExportModelAdmin
from audio_processing.tasks.batch_tasks import fetch_and_apply_groq_results_task
from audio_processing.tasks.podcast_tasks import process_podcast_by_id, index_podcast_for_search, reindex_all_podcasts_for_search
from audio_processing.tasks.entity_tasks import index_entity_for_search, reindex_all_entities_for_search
from django.db import models

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
        """Trigger async fetch and apply of Groq results for selected batches."""
        for batch in queryset:
            async_result = fetch_and_apply_groq_results_task.delay(batch.id)
            self.message_user(request, f"Batch {batch.id}: Task queued (Celery ID: {async_result.id})")
    fetch_and_apply_groq_results_action.short_description = "Fetch/apply Groq results for selected batches (async)"
    
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
        """Index selected entities to Meilisearch."""
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
    index_to_search.short_description = "Index selected entities to Meilisearch"

    def reindex_to_search(self, request, queryset):
        reindex_all_entities_for_search.delay()
        self.message_user(request, "Reindexing of all entities has been initiated.")

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
        """Process selected Podcasts."""
        for podcast in queryset:
            process_podcast_by_id.delay(podcast.id)
        self.message_user(request, f"Processing initiated for {queryset.count()} Podcasts.")
    process_feed.short_description = "Process selected Podcasts"

    def index_to_search(self, request, queryset):
        """Index selected podcasts to Meilisearch."""
        success_count = 0
        error_count = 0
        
        for podcast in queryset:
            try:
                index_podcast_for_search.delay(podcast.id)
            except Exception as e:
                error_count += 1
                self.message_user(request, f"Error indexing podcast '{podcast.name}': {str(e)}", level='ERROR')
        
        if success_count > 0:
            self.message_user(request, f"Successfully indexed {success_count} podcast(s) to Meilisearch.")
        
        if error_count > 0:
            self.message_user(request, f"{error_count} podcast(s) failed to index.", level='ERROR')
    index_to_search.short_description = "Index selected podcasts to Meilisearch"

    def reindex_to_search(self, request, queryset):
        reindex_all_podcasts_for_search.delay()
        self.message_user(request, "Reindexing of all podcasts has been initiated.")
    reindex_to_search.short_description = "Reindex all podcasts to Meilisearch"


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
               'suggest_tags', 'generate_speaker_scripts', 'run_complete_workflow', 'add_summary',
               'extract_quotes_action', 'index_to_search', 'extract_entities_action', 'batch_groq_transcribe', 'reindex_to_search', 'save_audio_to_s3_action']

    def save_audio_to_s3_action(self, request, queryset):
        """Admin action to save audio files to S3 for selected episodes."""
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
        """Batch transcribe selected episodes using Groq Batch API (async via Celery)."""
        from audio_processing.tasks.episode_tasks import groq_batch_transcribe
        episode_ids = list(queryset.values_list('id', flat=True))
        try:
            async_result = groq_batch_transcribe.delay(episode_ids)
            self.message_user(request, f"Batch transcription task queued. Celery Task ID: {async_result.id}")
        except Exception as e:
            self.message_user(request, f"Batch transcription failed: {str(e)}", level='ERROR')
    batch_groq_transcribe.short_description = "Batch transcribe (Groq) selected episodes (async)"

    def extract_entities_action(self, request, queryset):
        """Extract named entities from selected episodes."""
        success_count = 0
        error_count = 0
        no_transcript_count = 0
        from audio_processing.tasks.episode_tasks import extract_entities
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
        """Index selected episodes to Meilisearch."""
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
        # This could be enhanced to actually export data
        count = queryset.filter(transcript__isnull=False).exclude(transcript='').count()
        self.message_user(request, f"Found {count} episodes with transcripts to export.")
    export_transcripts.short_description = "Export transcripts for selected episodes"

    def fetch_transcript(self, request, queryset):
        """Fetch transcripts for selected episodes."""
        for episode in queryset:
            add_transcript.delay(episode.id)
        self.message_user(request, f"Transcript processing initiated for {queryset.count()} episodes.")
    fetch_transcript.short_description = "Fetch transcripts for selected episodes"

    def add_summary(self, request, queryset):
        """Generate summaries for selected episodes."""
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
    
    def suggest_tags(self, request, queryset):
        """Use AI to suggest and apply tags to selected episodes."""
        success_count = 0
        error_count = 0
        no_transcript_count = 0

        for episode in queryset:
            if not episode.transcript or not episode.transcript.strip():
                no_transcript_count += 1
                continue
            try:
                applied_tags = suggest_and_apply_tags.delay(episode.id)
            except Exception as e:
                error_count += 1
                self.message_user(
                    request, 
                    f"Error suggesting tags for {episode.raw_audio_url[:50]}...: {str(e)}", 
                    level='ERROR'
                )
        
        if success_count > 0:
            self.message_user(
                request, 
                f"Successfully suggested tags for {success_count} episodes."
            )
        
        if no_transcript_count > 0:
            self.message_user(
                request, 
                f"{no_transcript_count} episodes skipped (no transcript available).", 
                level='WARNING'
            )
        
        if error_count > 0:
            self.message_user(
                request, 
                f"{error_count} episodes failed to process.", 
                level='ERROR'
            )
    
    suggest_tags.short_description = "AI suggest and apply tags for selected episodes"

    def generate_speaker_scripts(self, request, queryset):
        """Generate speaker-attributed scripts for selected episodes."""
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
        """Run the complete workflow (transcript, tags, summary, speaker script) for selected podcasts."""
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
        """Extract memorable quotes from selected episodes."""
        success_count = 0
        error_count = 0
        no_transcript_count = 0
        
        for episode in queryset:
            if not episode.transcript or not episode.transcript.strip():
                no_transcript_count += 1
                continue
            
            try:
                extract_quotes.delay(episode.id)
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


@admin.register(Tag)
class TagAdmin(ImportExportModelAdmin):
    list_display = ('name', 'slug', 'color_display', 'podcast_count', 'podcast_count', 'created_at')
    list_filter = ('created_at', 'updated_at')
    search_fields = ('name', 'slug', 'description')
    readonly_fields = ('created_at', 'updated_at')
    prepopulated_fields = {'slug': ('name',)}
    
    def color_display(self, obj):
        """Display color as a colored box."""
        if obj.color:
            return f'<span style="background-color: {obj.color}; padding: 3px 8px; border-radius: 3px; color: white;">{obj.color}</span>'
        return '-'
    color_display.allow_tags = True
    color_display.short_description = 'Color'
    
    def episode_count(self, obj):
        return obj.episodes.count()
    episode_count.short_description = 'Episodes'

    def podcast_count(self, obj):
        return obj.podcasts.count()
    podcast_count.short_description = 'Podcasts'
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description')
        }),
        ('Appearance', {
            'fields': ('color',),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


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
    
    fieldsets = (
        ('Personal Information', {
            'fields': ('first_name', 'last_name', 'email')
        }),
        ('Podcast Association', {
            'fields': ('podcast',)
        }),
        ('Approval Status', {
            'fields': ('approval_status', 'approved_by', 'approval_notes')
        }),
        ('Status Dates', {
            'fields': ('date_approved', 'date_rejected'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    actions = ['approve_owners', 'reject_owners', 'reset_to_pending']
    
    def approve_owners(self, request, queryset):
        """Approve selected podcast owners."""
        count = 0
        for owner in queryset:
            if not owner.is_approved:
                owner.approve(approved_by=request.user)
                count += 1
        
        self.message_user(request, f"Approved {count} podcast owner(s).")
    approve_owners.short_description = "Approve selected podcast owners"
    
    def reject_owners(self, request, queryset):
        """Reject selected podcast owners."""
        count = 0
        for owner in queryset:
            if not owner.is_rejected:
                owner.reject(rejected_by=request.user)
                count += 1
        
        self.message_user(request, f"Rejected {count} podcast owner(s).")
    reject_owners.short_description = "Reject selected podcast owners"
    
    def reset_to_pending(self, request, queryset):
        """Reset selected podcast owners to pending status."""
        count = 0
        for owner in queryset:
            if not owner.is_pending:
                owner.reset_to_pending()
                count += 1
        
        self.message_user(request, f"Reset {count} podcast owner(s) to pending status.")
    reset_to_pending.short_description = "Reset selected owners to pending"


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

    actions = []

admin.site.register(Follow)
admin.site.register(Bookmark)


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'created_at', 'updated_at')
    search_fields = ('name', 'slug', 'description')
    readonly_fields = ('created_at', 'updated_at')
    prepopulated_fields = {'slug': ('name',)}
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'slug', 'description', 'top_words')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )