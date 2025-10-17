# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is "Retyped" - a Django-based backend for podcast audio processing and transcription. The system ingests podcast RSS feeds, processes audio files through various AI services (Groq for transcription, AWS Transcribe as alternative), and provides a REST API for accessing transcribed content with rich metadata including tags, entities, quotes, and summaries.

## Development Commands

All commands should be run through Docker Compose, as the project runs in containers:

### Running the Development Server
```bash
docker compose up webapp
```

### Database Operations
```bash
# Run migrations
docker compose exec webapp python manage.py migrate

# Create migrations
docker compose exec webapp python manage.py makemigrations

# Seed test data (creates admin user, test podcast, and tags)
docker compose exec webapp python manage.py seed
```

### Running Tests
```bash
# Run all tests
docker compose exec webapp python manage.py test

# Run specific test module
docker compose exec webapp python manage.py test audio_processing.tests.test_episode

# Run specific test class
docker compose exec webapp python manage.py test audio_processing.tests.test_episode.TestEpisodeClass

# Run with verbosity
docker compose exec webapp python manage.py test -v 2
```

### Celery Worker (for async tasks)
```bash
# Run a Celery worker locally
docker compose exec webapp celery -A audio_processing worker

# Or use the provided script
docker compose exec webapp ./celery_worker_endpoint.sh
```

### Django Shell
```bash
docker compose exec webapp python manage.py shell
```

### Database Shell
```bash
docker compose exec webapp python manage.py dbshell
```

## Architecture Overview

### Core Models and Their Responsibilities

**Podcast** (`audio_processing/models/podcast.py`)
- Represents a podcast RSS feed
- Fetches and parses RSS feeds via `fetch_feed()` and `update_from_feed()`
- Creates Episode instances from RSS entries via `process_feed()`
- Uses SearchableMixin for Meilisearch integration

**Episode** (`audio_processing/models/episode.py`)
- Represents a single podcast episode
- Inherits multiple mixins: GroqMixin, AwsMixin, TaggableMixin, SummarizableMixin, SearchableMixin, QuotableMixin
- Complete processing workflow via `process_complete_workflow()`:
  1. Upload audio to S3 (`upload_audio_to_s3()`)
  2. Generate transcript (`generate_transcript()` - supports Groq and AWS Transcribe)
  3. Apply tags (`suggest_and_apply_tags()` from TaggableMixin)
  4. Generate speaker script (`generate_speaker_script()` from GroqMixin)
  5. Generate summary (`generate_summary()` from SummarizableMixin)
  6. Extract entities (`extract_entities()`)
  7. Extract quotes (`extract_quotes()` from QuotableMixin)
  8. Index to search (`index_to_search()` from SearchableMixin)

**Entity** (`audio_processing/models/entity.py`)
- Represents named entities (people, organizations, etc.) extracted from transcripts
- Many-to-many relationship with Episodes

**Tag** (`audio_processing/models/tag.py`)
- Simple tagging system for podcasts and episodes

**Topic** (`audio_processing/models/topic.py`)
- Topic modeling for episodes (requires HF_API_TOKEN for Hugging Face)

**PodcastClaim & ClaimVerification** (`audio_processing/models/podcast_claim.py`, `audio_processing/models/claim_verification.py`)
- Fact-checking system for claims made in podcasts

### Mixin Architecture

The codebase uses a mixin pattern to compose model functionality (`audio_processing/models/mixins/`):

- **GroqMixin**: Groq API integration for transcription and speaker diarization
- **AwsMixin**: AWS Transcribe integration for audio transcription
- **TaggableMixin**: AI-powered tag suggestion and application using Groq
- **SummarizableMixin**: Episode summary generation using Groq
- **SearchableMixin**: Meilisearch integration for full-text search
- **QuotableMixin**: Extract memorable quotes from transcripts using Groq

### Async Task Processing

Celery is used for long-running tasks (`audio_processing/tasks/`):

- **episode_tasks.py**: Episode processing tasks (transcription, tagging, entity extraction, quote extraction)
- **podcast_tasks.py**: Podcast feed processing tasks
- **batch_tasks.py**: Batch processing operations
- **entity_tasks.py**: Entity extraction tasks

Key task patterns:
- Tasks follow naming convention: action + noun (e.g., `process_complete_workflow`, `add_transcript`)
- All tasks use `@shared_task` decorator
- Error handling includes logging and storing errors on Episode model

### API Structure

REST API is versioned under `/api/v1/` (see `audio_processing/api_urls.py`):

- **Episodes**: List, retrieve by slug, top by views
- **Podcasts**: List, retrieve by slug, episodes list, top by views
- **Tags**: List, retrieve, get related episodes/podcasts
- **Entities**: List, get related episodes/podcasts
- **Search**: Full-text search across episodes and podcasts (Meilisearch)
- **Bookmarks**: User bookmarks for episodes/podcasts
- **Follows**: User follows for podcasts
- **UserAnalytics**: User listening analytics

ViewSets use DRF's APIView pattern with explicit action methods (e.g., `as_view({"get": "list"})`)

### Settings Architecture

Settings are split into environment-specific files:
- `audio_processing/settings/base.py`: Common settings
- `audio_processing/settings/dev.py`: Development overrides (loads `.env.dev`)
- `audio_processing/settings/prod.py`: Production overrides

Always specify settings module: `DJANGO_SETTINGS_MODULE=audio_processing.settings.dev`

### External Service Integration

**Groq** (Primary AI provider):
- Transcription via Whisper models
- Tag/summary generation via Llama models
- Speaker diarization
- Model selection via Constance dynamic config

**AWS Services**:
- S3 for audio file storage
- Transcribe for alternative transcription

**Meilisearch**:
- Full-text search for episodes and podcasts
- Runs on port 7700 (see docker-compose.yml)

**OAuth Providers**:
- Google, Facebook, Twitter, Instagram via django-social-auth

### Database

- PostgreSQL 17 (via Docker Compose)
- Connection details in `.env.dev`
- Migrations in `audio_processing/migrations/`

## Important Patterns

### Model Save Override Pattern
Both Podcast and Episode override `save()` to auto-generate slugs:
```python
def save(self, *args, **kwargs):
    if not self.slug and self.title:
        # Generate unique slug
        base_slug = slugify(self.title)
        # ... uniqueness check
    super().save(*args, **kwargs)
```

### Search Indexing Pattern
Models using SearchableMixin must implement:
```python
def get_search_document(self):
    return {
        "id": self.id,
        "title": self.title,
        # ... other searchable fields
    }
```
Indexing happens automatically after save via `index_to_search()`.

### Async Processing Pattern
For heavy operations, create Celery tasks:
```python
@shared_task
def process_episode(episode_id):
    episode = Episode.objects.get(pk=episode_id)
    return episode.process_complete_workflow()
```

### Environment Variables
Key environment variables (see `.env.example`):
- `GROQ_API_KEY`: Groq API key for AI features
- `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`: AWS credentials
- `MEILISEARCH_URL`, `MEILISEARCH_API_KEY`: Search service config
- Database connection: `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT`

## Common Development Workflows

### Adding a New Model Field
1. Add field to model in `audio_processing/models/`
2. Run `docker compose exec webapp python manage.py makemigrations`
3. Review migration file
4. Run `docker compose exec webapp python manage.py migrate`
5. If searchable, update `get_search_document()` method

### Adding a New API Endpoint
1. Create serializer in `audio_processing/serializers/`
2. Create viewset in `audio_processing/views/`
3. Add URL pattern to `audio_processing/api_urls.py`
4. Test via `/swagger/` documentation endpoint

### Processing a New Podcast
1. Add podcast via Django admin at `/admin/`
2. Run `podcast.process_feed()` or trigger via Celery task
3. Episodes are auto-created and queued for processing
4. Monitor processing via logs or admin interface

## API Documentation

Interactive API docs available at:
- Swagger UI: `http://localhost:8000/swagger/`
- ReDoc: `http://localhost:8000/redoc/`

## Test Data

Default test credentials (created by seed command):
- Username: `admin`
- Password: `admin123`
