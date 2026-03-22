import json
import logging
import mimetypes
import os
import tempfile
import time
import uuid
from urllib.parse import urlparse, urlunparse

import boto3
import requests
from constance import config
from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from groq import Groq

from audio_processing.models.mixins import (
    QuotableMixin,
    SearchableMixin,
    SummarizableMixin,
    TaggableMixin,
)

from .mixins.aws_mixin import AwsMixin
from .mixins.groq_mixin import GroqMixin

logger = logging.getLogger(__name__)
transcribe_client = boto3.client("transcribe", region_name="us-east-1")


class Episode(
    models.Model,
    GroqMixin,
    AwsMixin,
    TaggableMixin,
    SummarizableMixin,
    SearchableMixin,
    QuotableMixin,
):
    s3_audio_url = models.URLField(
        max_length=2000,
        blank=True,
        null=True,
        help_text="S3 URI of the uploaded audio file",
    )
    processing_completed_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Timestamp when episode processing was completed",
    )
    image_url = models.URLField(
        max_length=1000, blank=True, null=True, help_text="Episode artwork URL"
    )
    slug = models.SlugField(
        max_length=512,
        unique=True,
        blank=True,
        help_text="Unique slug for episode, prefixed with podcast slug",
    )
    # Search configuration
    SEARCH_INDEX_UID = "episodes"
    # Relationship
    podcast = models.ForeignKey(
        "Podcast",
        on_delete=models.CASCADE,
        related_name="episodes",
        blank=True,
        null=True,
        help_text="Podcast this episode belongs to",
    )

    # Basic episode info
    title = models.CharField(
        max_length=512,
        blank=True,
        null=True,
        db_index=True,
        help_text="Title of the podcast episode",
    )
    description = models.TextField(
        blank=True, null=True, help_text="Episode description"
    )
    subtitle = models.CharField(
        max_length=2000, blank=True, null=True, help_text="Episode subtitle"
    )

    # Audio information
    raw_audio_url = models.URLField(
        max_length=2000, unique=True, help_text="URL of the raw audio file"
    )
    audio_type = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        help_text="Audio MIME type (e.g., audio/mpeg)",
    )
    audio_length = models.BigIntegerField(
        blank=True, null=True, help_text="Audio file size in bytes"
    )
    duration = models.DurationField(blank=True, null=True, help_text="Episode duration")

    # Episode metadata
    episode_number = models.IntegerField(
        blank=True, null=True, help_text="Episode number"
    )
    season_number = models.IntegerField(
        blank=True, null=True, help_text="Season number"
    )
    episode_type = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        help_text="Episode type (full, trailer, bonus)",
    )
    has_public_transcript = models.BooleanField(
        default=False, help_text="Whether the episode has a public transcript"
    )

    # iTunes specific
    itunes_explicit = models.BooleanField(
        default=False, help_text="iTunes explicit content flag for episode"
    )
    itunes_episode_type = models.CharField(
        max_length=20, blank=True, null=True, help_text="iTunes episode type"
    )

    # Episode content
    content_encoded = models.TextField(
        blank=True, null=True, help_text="HTML encoded content/show notes"
    )

    # Processing fields
    transcript = models.TextField(
        blank=True, null=True, help_text="Raw transcript from speech-to-text"
    )
    script_transcript = models.TextField(
        blank=True,
        null=True,
        help_text="Formatted transcript with speaker identification",
    )
    summary = models.TextField(
        blank=True, null=True, help_text="AI-generated summary of the episode"
    )

    # Dates
    release_date = models.DateTimeField(
        blank=True, null=True, help_text="Original release date of the podcast episode"
    )
    pub_date = models.DateTimeField(
        blank=True, null=True, help_text="Publication date from RSS"
    )

    # System fields
    tags = models.ManyToManyField(
        "Tag",
        blank=True,
        related_name="episodes",
        help_text="Tags associated with this episode",
    )
    error = models.TextField(
        blank=True, null=True, help_text="Error message if processing failed"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    entities = models.ManyToManyField(
        "Entity",
        blank=True,
        related_name="episodes",
        help_text="Entities associated with this episode",
    )
    topics = models.ManyToManyField(
        "Topic",
        blank=True,
        related_name="episodes",
        help_text="Topics associated with this episode",
    )

    def __str__(self):
        if self.title:
            return self.title
        elif self.podcast and self.podcast.name:
            return f"{self.podcast.name} - Episode"
        else:
            return f"Episode {self.id or 'New'}"

    def save(self, *args, **kwargs):
        # Clean audio URL
        if self.raw_audio_url:
            self.raw_audio_url = self.clean_url(self.raw_audio_url)
        # Generate slug if not set
        if not self.slug and self.title and self.podcast and self.podcast.slug:
            base_slug = f"{self.podcast.slug}-{slugify(self.title)}"
            slug = base_slug
            counter = 1
            while Episode.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        if self.raw_audio_url:
            self.raw_audio_url = self.clean_url(self.raw_audio_url)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return "/shows/" + self.podcast.slug + "/" + self.slug

    @classmethod
    def create_from_entry(cls, podcast, entry):
        """
        Creates a podcast episode from an RSS entry.
        Returns the created/existing Episode object or None if failed.
        """
        logger = logging.getLogger(__name__)
        title = entry.get("title", "No Title")
        logger.info(f"Processing episode entry: {title}")

        # Extract audio URL and metadata from enclosures
        audio_url = None
        audio_type = None
        audio_length = None
        image_url = None

        if hasattr(entry, "enclosures") and entry.enclosures:
            for enclosure in entry.enclosures:
                if enclosure.get("type", "").startswith("audio/"):
                    audio_url = enclosure.get("href")
                    audio_type = enclosure.get("type")
                    audio_length = enclosure.get("length")
                    if audio_length:
                        try:
                            audio_length = int(audio_length)
                        except (ValueError, TypeError):
                            audio_length = None
                    break

        # Try to get image URL from entry (standard or iTunes)
        if hasattr(entry, "image") and getattr(entry, "image", None):
            if hasattr(entry.image, "href"):
                image_url = entry.image.href
            elif hasattr(entry.image, "url"):
                image_url = entry.image.url
        elif hasattr(entry, "itunes_image") and getattr(entry, "itunes_image", None):
            if hasattr(entry.itunes_image, "href"):
                image_url = entry.itunes_image.href
            elif hasattr(entry.itunes_image, "url"):
                image_url = entry.itunes_image.url
        elif "image" in entry and getattr(entry, "image", None):
            image_url = entry.get("image")

        # Fallback: check for links that might be audio files
        if not audio_url and hasattr(entry, "links"):
            for link in entry.links:
                if link.get("type", "").startswith("audio/"):
                    audio_url = link.get("href")
                    audio_type = link.get("type")
                    break

        if not audio_url:
            logger.warning(f"No audio URL found for entry: {title}")
            return None

        # Extract dates
        release_date = None
        pub_date = None

        if hasattr(entry, "published_parsed") and entry.published_parsed:
            try:
                import time
                from datetime import datetime

                timestamp = time.mktime(entry.published_parsed)
                pub_date = datetime.fromtimestamp(
                    timestamp, tz=timezone.get_current_timezone()
                )
                release_date = (
                    pub_date  # Use pub_date as release_date for backward compatibility
                )
            except Exception as e:
                logger.warning(
                    f"Failed to parse published date for entry '{title}': {str(e)}"
                )

        # Fallback: try 'updated_parsed' if 'published_parsed' is not available
        if (
            not release_date
            and hasattr(entry, "updated_parsed")
            and entry.updated_parsed
        ):
            try:
                timestamp = time.mktime(entry.updated_parsed)
                release_date = datetime.fromtimestamp(
                    timestamp, tz=timezone.get_current_timezone()
                )
                if not pub_date:
                    pub_date = release_date
            except Exception as e:
                logger.warning(
                    f"Failed to parse updated date for entry '{title}': {str(e)}"
                )

        # Check if episode already exists
        existing_episode = cls.objects.filter(title=title, podcast=podcast).first()
        if not existing_episode:
            existing_episode = cls.objects.filter(raw_audio_url=audio_url).first()
        if existing_episode:
            # Update missing fields
            updated = podcast._update_existing_episode(
                existing_episode,
                entry,
                title,
                audio_type,
                audio_length,
                release_date,
                pub_date,
            )
            if updated:
                logger.info(f"Updated existing episode: {title}")
            return existing_episode

        # Create new episode with all the rich metadata
        episode_data = {
            "podcast": podcast,
            "title": title,
            "raw_audio_url": audio_url,
            "audio_type": audio_type,
            "audio_length": audio_length,
            "release_date": release_date,
            "pub_date": pub_date,
            "image_url": image_url,
        }

        # Add optional fields from entry
        if hasattr(entry, "summary") and entry.summary:
            episode_data["description"] = entry.summary

        if hasattr(entry, "subtitle") and entry.subtitle:
            episode_data["subtitle"] = entry.subtitle[:2000]

        if hasattr(entry, "itunes_episode") and entry.itunes_episode:
            try:
                episode_data["episode_number"] = int(entry.itunes_episode)
            except (ValueError, TypeError):
                pass

        if hasattr(entry, "itunes_season") and entry.itunes_season:
            try:
                episode_data["season_number"] = int(entry.itunes_season)
            except (ValueError, TypeError):
                pass

        if hasattr(entry, "itunes_episodetype") and entry.itunes_episodetype:
            episode_data["episode_type"] = entry.itunes_episodetype

        if hasattr(entry, "itunes_explicit"):
            episode_data["itunes_explicit"] = entry.itunes_explicit == "yes"

        # if hasattr(entry, 'tags') and entry.tags:
        #     episode_data['itunes_keywords'] = [tag.term for tag in entry.tags if hasattr(tag, 'term')]

        if hasattr(entry, "content") and entry.content:
            # Get the first content item (usually HTML)
            if len(entry.content) > 0:
                episode_data["content_encoded"] = entry.content[0].get("value", "")

        if hasattr(entry, "transcript") and entry.transcript:
            episode_data["has_public_transcript"] = True

        if hasattr(entry, "itunes_duration") and entry.itunes_duration:
            try:
                # Parse duration (format: HH:MM:SS or MM:SS or seconds)
                duration_str = entry.itunes_duration
                parts = duration_str.split(":")
                if len(parts) == 3:  # HH:MM:SS
                    hours, minutes, seconds = map(int, parts)
                    total_seconds = hours * 3600 + minutes * 60 + seconds
                elif len(parts) == 2:  # MM:SS
                    minutes, seconds = map(int, parts)
                    total_seconds = minutes * 60 + seconds
                else:  # Just seconds
                    total_seconds = int(duration_str)
                from datetime import timedelta

                episode_data["duration"] = timedelta(seconds=total_seconds)
            except (ValueError, TypeError):
                pass

        episode = cls.objects.create(**episode_data)
        logger.info(
            f"Created episode: {title} - {audio_url} (released: {release_date})"
        )
        return episode

    @property
    def public_transcript_allowed(self):
        """
        Determine if this episode's transcript can be made public.
        Returns True if either:
        1. The episode has_public_transcript is True, OR
        2. The podcast owner is approved
        """
        # First check if the episode itself has public transcript enabled
        if self.has_public_transcript:
            return True

        # If not, check if the podcast has an approved owner
        if self.podcast and hasattr(self.podcast, "owner"):
            try:
                return self.podcast.owner.is_approved
            except AttributeError:
                # In case owner doesn't exist or is_approved property is missing
                pass

        # Default to False if neither condition is met
        return False

    def clean_url(self, url):
        """
        Remove URL parameters from the given URL.
        Returns the clean URL without query parameters.
        """
        if not url:
            return url

        try:
            parsed = urlparse(url)
            # Reconstruct URL without query parameters
            clean_url = urlunparse(
                (
                    parsed.scheme,
                    parsed.netloc,
                    parsed.path,
                    parsed.params,
                    "",  # Remove query string
                    "",  # Remove fragment
                )
            )
            return clean_url
        except Exception as e:
            logger.warning(f"Failed to clean URL {url}: {str(e)}")
            return url

    def upload_audio_to_s3(self, audio_url):
        """
        Upload audio file from URL to S3 and return the S3 URI.
        Returns the S3 URI or None if failed.
        """
        try:
            from botocore.exceptions import ClientError, NoCredentialsError

            # Get S3 configuration
            bucket_name = getattr(settings, "AWS_S3_BUCKET", None)
            if not bucket_name:
                logger.error("AWS_S3_BUCKET not configured")
                return None

            # Initialize S3 client
            s3_client = boto3.client(
                "s3",
                region_name=getattr(settings, "AWS_REGION", "us-east-1"),
                aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
                aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
            )

            # Download the audio file
            logger.info(f"Downloading audio file from: {audio_url}")
            response = requests.get(audio_url, stream=True, timeout=300)
            response.raise_for_status()

            # Determine file extension from URL or Content-Type
            parsed_url = urlparse(audio_url)
            file_extension = None

            # Try to get extension from URL path
            if "." in parsed_url.path:
                file_extension = parsed_url.path.split(".")[-1].lower()
                # Clean common query parameters that might be appended
                if "?" in file_extension:
                    file_extension = file_extension.split("?")[0]

            # If no extension from URL, try to determine from Content-Type
            if not file_extension:
                content_type = response.headers.get("content-type", "")
                if content_type:
                    extension = mimetypes.guess_extension(content_type)
                    if extension:
                        file_extension = extension.lstrip(".")

            # Default to mp3 if we can't determine the format
            if not file_extension:
                file_extension = "mp3"

            # Ensure valid audio file extension
            valid_extensions = ["mp3", "wav", "m4a", "flac", "ogg", "aac", "mp4"]
            if file_extension not in valid_extensions:
                logger.warning(
                    f"Unknown audio file extension: {file_extension}, defaulting to mp3"
                )
                file_extension = "mp3"

            # Generate unique S3 key
            unique_id = uuid.uuid4().hex[:8]
            s3_key = f"audio/episode-{unique_id}.{file_extension}"

            # Determine content type for S3 upload
            content_type = response.headers.get(
                "content-type", f"audio/{file_extension}"
            )

            # Upload to S3
            logger.info(f"Uploading audio file to S3: s3://{bucket_name}/{s3_key}")
            s3_client.upload_fileobj(
                response.raw,
                bucket_name,
                s3_key,
                ExtraArgs={
                    "ContentType": content_type,
                    "Metadata": {
                        "original_url": audio_url[
                            :1000
                        ],  # Truncate to avoid metadata limits
                        "episode_id": str(self.id) if self.id else "new",
                        "upload_timestamp": str(time.time()),
                    },
                },
            )

            # Return S3 URI
            s3_uri = f"s3://{bucket_name}/{s3_key}"
            logger.info(f"Audio file uploaded successfully to: {s3_uri}")
            self.s3_audio_url = "https://cdn.retyped.xyz/" + s3_key
            self.save(update_fields=["s3_audio_url"])
            return self.s3_audio_url

        except NoCredentialsError:
            logger.error("AWS credentials not configured for S3 upload")
            return None
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "Unknown")
            logger.error(f"AWS S3 client error during upload ({error_code}): {str(e)}")
            return None
        except requests.exceptions.Timeout:
            logger.error(f"Timeout downloading audio file from {audio_url}")
            return None
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to download audio file from {audio_url}: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Failed to upload audio to S3: {str(e)}")
            return None

    def generate_transcript(self, method="groq"):
        """
        Generate transcript using the specified method or auto-detect best available.

        Args:
            method (str): 'groq', 'aws', or 'auto' to choose automatically

        Returns:
            str: The transcript text or None if failed
        """
        logger.info(
            f"Generating transcript for: {self.raw_audio_url} using method: {method}"
        )

        if method == "auto":
            # Auto-select based on available configuration
            groq_key = getattr(settings, "GROQ_API_KEY", None)
            aws_configured = all(
                [
                    getattr(settings, "AWS_ACCESS_KEY_ID", None),
                    getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
                ]
            )

            if groq_key:
                method = "groq"
                logger.info("Auto-selected Groq for transcription")
            elif aws_configured:
                method = "aws"
                logger.info("Auto-selected AWS Transcribe for transcription")
            else:
                logger.error(
                    "No transcription service configured (GROQ_API_KEY or AWS credentials)"
                )
                return None

        if method == "groq":
            return self.get_transcript_from_groq()
        elif method == "aws":
            return self.get_transcript_from_aws()
        else:
            logger.error(f"Unknown transcription method: {method}")
            return None

    def process_complete_workflow(self):
        """
        Complete workflow: generate transcript, apply tags, create speaker script, generate summary, extract entities, and extract quotes.
        Returns a summary of what was accomplished.
        """
        results = {
            "transcript_generated": False,
            "tags_applied": 0,
            "script_generated": False,
            "summary_generated": False,
            "entities_extracted": 0,
            "quotes_extracted": 0,
            "errors": [],
        }
        # Step 0: Save audio to S3 if not already done
        if not self.s3_audio_url:
            s3_uri = self.upload_audio_to_s3(self.raw_audio_url)
            if s3_uri:
                logger.info(f"Audio saved to S3: {s3_uri}")
            else:
                results["errors"].append("Failed to save audio to S3")
                return results

        # Step 1: Generate transcript if needed
        if not self.transcript:
            transcript = self.generate_transcript()
            if transcript:
                results["transcript_generated"] = True
                logger.info(f"Transcript generated for: {self.raw_audio_url}")
            else:
                results["errors"].append("Failed to generate transcript")
                return results
        # Step 2: Apply tags
        applied_tags = self.suggest_and_apply_tags()
        if applied_tags:
            results["tags_applied"] = len(applied_tags)
            logger.info(f"Applied {len(applied_tags)} tags to: {self.raw_audio_url}")
        else:
            results["errors"].append("Failed to apply tags")
        # Step 3: Generate speaker script
        script = self.generate_speaker_script()
        if script:
            results["script_generated"] = True
            logger.info(f"Speaker script generated for: {self.raw_audio_url}")
        else:
            results["errors"].append("Failed to generate speaker script")
        # Step 4: Generate episode summary
        summary = self.generate_summary()
        if summary:
            results["summary_generated"] = True
            logger.info(f"Episode summary generated for: {self.raw_audio_url}")
        else:
            results["errors"].append("Failed to generate episode summary")
        # Step 5: Extract entities
        entities = self.extract_entities()
        if entities:
            results["entities_extracted"] = len(entities)
            logger.info(
                f"Extracted {len(entities)} entities from: {self.raw_audio_url}"
            )
        else:
            results["errors"].append("Failed to extract entities")
        # Step 6: Extract key quotes
        quotes = self.extract_quotes()
        if quotes:
            results["quotes_extracted"] = len(quotes)
            logger.info(f"Extracted {len(quotes)} quotes from: {self.raw_audio_url}")
        else:
            results["errors"].append("Failed to extract quotes")
        self.processing_completed_at = timezone.now()
        self.save(update_fields=["processing_completed_at"])
        self.index_to_search()
        return results

    def get_search_document(self):
        """
        Prepare episode data for search indexing.

        Returns:
            dict: Document data to be indexed, or None if not indexable
        """
        # Prepare document data
        return {
            "id": self.id,
            "title": self.title or "Untitled Episode",
            "transcript": self.transcript,
            "summary": self.summary or "",
            "raw_audio_url": self.raw_audio_url,
            "release_date": self.release_date.isoformat()
            if self.release_date
            else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "podcast_name": self.podcast.name if self.podcast else None,
            "tags": [tag.name for tag in self.tags.all()],
        }

    def extract_entities(self):
        """
        Extract named entities from the episode transcript using Groq and associate them to this episode.
        Returns a list of Entity instances.
        """
        from audio_processing.models.entity import Entity

        if not self.transcript:
            return []
        return Entity.entities_from_text(self.transcript, related_obj=self)

    @staticmethod
    def groq_batch_transcribe(episode_ids):
        """
        Batch transcribe a list of episode IDs using Groq's Batch API.
        Generates a JSONL file for batch processing and uploads it to Groq.
        Args:
            episode_ids (list): List of Episode IDs to transcribe
        Returns:
            dict: Groq file upload response
        """
        from audio_processing.models import ProcessingBatch

        # Prepare JSONL lines
        lines = []
        for eid in episode_ids:
            try:
                episode = Episode.objects.get(pk=eid)
                if not episode.s3_audio_url:
                    s3_uri = episode.upload_audio_to_s3(episode.raw_audio_url)
                else:
                    s3_uri = episode.s3_audio_url
                line = {
                    "custom_id": f"episode-{eid}",
                    "method": "POST",
                    "url": "/v1/audio/transcriptions",
                    "body": {
                        "model": config.TEXT_TO_SPEECH_MODEL,
                        "language": "en",
                        "url": s3_uri,
                        "response_format": "verbose_json",
                        "timestamp_granularities": ["segment"],
                    },
                }
                lines.append(json.dumps(line))
            except Episode.DoesNotExist:
                continue

        # Write JSONL file to a temp file
        with tempfile.NamedTemporaryFile(
            mode="w+b", suffix=".jsonl", delete=False
        ) as tmpfile:
            for line in lines:
                tmpfile.write((line + "\n").encode("utf-8"))
            tmpfile.flush()
            tmpfile_path = tmpfile.name

        # Upload file to Groq Files API
        groq_api_key = getattr(settings, "GROQ_API_KEY", os.environ.get("GROQ_API_KEY"))
        if not groq_api_key:
            raise Exception("GROQ_API_KEY not configured in settings or environment.")

        files_url = "https://api.groq.com/openai/v1/files"
        with open(tmpfile_path, "rb") as file_data:
            response = requests.post(
                files_url,
                headers={"Authorization": f"Bearer {groq_api_key}"},
                files={"file": (os.path.basename(tmpfile_path), file_data)},
                data={"purpose": "batch"},
            )
        response.raise_for_status()
        # Optionally, clean up the temp file
        os.remove(tmpfile_path)
        groq_response = response.json()
        file_id = groq_response.get("id")

        client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

        batch = client.batches.create(
            completion_window="24h",
            endpoint="/v1/chat/completions",
            input_file_id=file_id,
        )

        # Create ProcessingBatch record
        batch = ProcessingBatch.objects.create(
            external_batch_id=batch.id, record_count=len(episode_ids)
        )
        return groq_response
