from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, TestCase, override_settings
from groq import RateLimitError

from audio_processing.models import Podcast
from audio_processing.models.mixins import audio_chunking
from audio_processing.tasks.podcast_tasks import (
    process_all_active_podcasts,
    process_podcast_by_id,
)
from audio_processing.utils.storage import (
    audio_download_url,
    get_s3_client,
    public_audio_url,
)


class StorageTest(SimpleTestCase):
    @override_settings(AWS_S3_ENDPOINT_URL=None, AWS_REGION="us-east-1")
    def test_s3_client_uses_aws_by_default(self):
        client = get_s3_client()
        self.assertEqual(client.meta.region_name, "us-east-1")
        self.assertIn("amazonaws.com", client.meta.endpoint_url)

    @override_settings(AWS_S3_ENDPOINT_URL="https://account.r2.cloudflarestorage.com")
    def test_s3_client_uses_custom_endpoint(self):
        client = get_s3_client()
        self.assertEqual(
            client.meta.endpoint_url, "https://account.r2.cloudflarestorage.com"
        )
        self.assertEqual(client.meta.region_name, "auto")

    @override_settings(AUDIO_CDN_URL="https://media.example.com")
    def test_public_audio_url(self):
        self.assertEqual(
            public_audio_url("audio/episode-1.mp3"),
            "https://media.example.com/audio/episode-1.mp3",
        )

    @override_settings(
        AUDIO_CDN_URL="https://media.example.com",
        AWS_S3_BUCKET="audio-bucket",
        AWS_S3_ENDPOINT_URL=None,
        AWS_REGION="us-east-1",
        AWS_ACCESS_KEY_ID="test-key",
        AWS_SECRET_ACCESS_KEY="test-secret",
    )
    def test_audio_download_url_presigns_cdn_urls(self):
        url = audio_download_url("https://media.example.com/audio/episode-1.mp3")
        self.assertIn("audio-bucket", url)
        self.assertIn("audio/episode-1.mp3", url)
        self.assertIn("X-Amz-Signature=", url)
        self.assertNotIn("media.example.com", url)

    @override_settings(AUDIO_CDN_URL="https://media.example.com")
    def test_audio_download_url_passes_other_urls_through(self):
        feed_url = "https://feeds.example.org/episode.mp3"
        self.assertEqual(audio_download_url(feed_url), feed_url)
        self.assertIsNone(audio_download_url(None))


class ProcessAllActivePodcastsTest(TestCase):
    def test_queues_one_task_per_active_podcast(self):
        active = Podcast.objects.create(name="Active", url="https://a.example/rss")
        Podcast.objects.create(
            name="Inactive", url="https://b.example/rss", is_active=False
        )
        with patch.object(process_podcast_by_id, "delay") as delay:
            result = process_all_active_podcasts()
        delay.assert_called_once_with(active.id)
        self.assertEqual(result, {"total_feeds_queued": 1})


class RateLimitRetryTest(SimpleTestCase):
    def test_gives_up_after_max_retries(self):
        client = MagicMock()
        client.audio.transcriptions.create.side_effect = RateLimitError(
            "rate limited", response=MagicMock(status_code=429), body=None
        )
        chunk = MagicMock()
        with (
            patch.object(audio_chunking.time, "sleep") as sleep,
            self.assertRaises(RateLimitError),
        ):
            audio_chunking.transcribe_single_chunk(client, chunk, 1, 1)
        self.assertEqual(sleep.call_count, audio_chunking.MAX_RATE_LIMIT_RETRIES)
