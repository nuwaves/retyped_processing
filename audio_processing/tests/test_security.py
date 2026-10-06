from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from audio_processing.models import Episode, Podcast
from audio_processing.serializers.episodes import ANONYMOUS_TRANSCRIPT_PREVIEW_CHARS
from audio_processing.tasks.podcast_tasks import index_podcast_for_search
from audio_processing.utils import sanitize_html_content


class SanitizeHtmlContentTest(TestCase):
    def test_keeps_basic_formatting(self):
        html = (
            '<p>Hello <strong>world</strong> <a href="https://example.com">link</a></p>'
        )
        cleaned = sanitize_html_content(html)
        self.assertIn("<strong>world</strong>", cleaned)
        self.assertIn('href="https://example.com"', cleaned)

    def test_removes_scripts_and_event_handlers(self):
        cleaned = sanitize_html_content(
            '<p onclick="alert(1)">hi</p><script>alert(1)</script><img src=x onerror=alert(1)>'
        )
        self.assertNotIn("script", cleaned)
        self.assertNotIn("alert", cleaned)
        self.assertNotIn("onclick", cleaned)
        self.assertNotIn("onerror", cleaned)

    def test_removes_obfuscated_javascript_urls(self):
        for href in [
            "javascript:alert(1)",
            "JaVaScRiPt:alert(1)",
            "java&#x09;script:alert(1)",
            "&#106;avascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
        ]:
            with self.subTest(href=href):
                cleaned = sanitize_html_content(f'<a href="{href}">x</a>')
                self.assertNotIn("href", cleaned)

    def test_removes_class_and_style_attributes(self):
        cleaned = sanitize_html_content(
            '<div class="fixed inset-0" style="position:fixed">x</div>'
        )
        self.assertEqual(cleaned, "<div>x</div>")

    def test_empty_value_returns_none(self):
        self.assertIsNone(sanitize_html_content(""))
        self.assertIsNone(sanitize_html_content(None))


class EpisodeSerializerExposureTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="reader", password="testpass")
        self.podcast = Podcast.objects.create(
            name="Podcast", url="https://example.com/feed", description="<p>Show</p>"
        )
        self.transcript = "word " * 500
        self.episode = Episode.objects.create(
            title="Episode",
            slug="episode",
            podcast=self.podcast,
            raw_audio_url="https://example.com/audio.mp3",
            s3_audio_url="https://cdn.example.com/audio.mp3",
            transcript=self.transcript,
            script_transcript=self.transcript,
            error="Traceback: internal detail",
            description='<p>Notes</p><img src=x onerror="alert(1)">',
        )
        self.url = f"/api/v1/episodes/{self.episode.slug}/"

    def test_internal_fields_are_not_returned(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("error", response.data)
        self.assertNotIn("s3_audio_url", response.data)
        self.assertEqual(response.data["raw_audio_url"], self.episode.raw_audio_url)

    def test_anonymous_users_get_transcript_preview(self):
        response = self.client.get(self.url)
        self.assertEqual(
            len(response.data["transcript"]), ANONYMOUS_TRANSCRIPT_PREVIEW_CHARS
        )
        self.assertEqual(
            len(response.data["script_transcript"]),
            ANONYMOUS_TRANSCRIPT_PREVIEW_CHARS,
        )

    def test_authenticated_users_get_full_transcript(self):
        self.client.force_authenticate(user=self.user)
        response = self.client.get(self.url)
        self.assertEqual(response.data["transcript"], self.transcript)
        self.assertEqual(response.data["script_transcript"], self.transcript)

    def test_episode_description_is_sanitized(self):
        response = self.client.get(self.url)
        self.assertNotIn("onerror", response.data["description"])

    def test_podcast_description_is_sanitized(self):
        self.podcast.description = "<p>Show</p><script>alert(1)</script>"
        self.podcast.save()
        response = self.client.get(f"/api/v1/podcasts/{self.podcast.slug}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["description"], "<p>Show</p>")


class IndexPodcastForSearchTest(TestCase):
    def test_indexes_podcast_without_requeueing(self):
        podcast = Podcast.objects.create(name="Podcast", url="https://example.com/rss")
        with (
            patch.object(Podcast, "index_to_search") as index_to_search,
            patch.object(index_podcast_for_search, "delay") as delay,
        ):
            result = index_podcast_for_search(podcast.id)
        index_to_search.assert_called_once_with()
        delay.assert_not_called()
        self.assertIn("success", result)
