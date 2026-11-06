"""Tests for the top-chart catalog: chart import, sitemap, list filter, search."""

from unittest.mock import Mock, patch
from xml.etree import ElementTree

from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from audio_processing.chart_import import feed_key, import_top_chart
from audio_processing.models import Episode, Podcast

CHART = {
    "feed": {
        "results": [
            {"id": "111", "name": "New Show"},
            {"id": "222", "name": "Known Show"},
            {"id": "333", "name": "Apple Exclusive"},
            {"id": "444", "name": "Renamed Feed"},
        ]
    }
}
LOOKUP = {
    "results": [
        {"collectionId": 111, "feedUrl": "https://feeds.example.com/new"},
        # Same feed as an existing podcast, apart from scheme, www and slash.
        {"collectionId": 222, "feedUrl": "http://www.example.com/known/"},
        {"collectionId": 333},
        {"collectionId": 444, "feedUrl": "https://other.example.com/renamed"},
    ]
}


def fake_get(url, params=None, **kwargs):
    resp = Mock()
    resp.raise_for_status = Mock()
    resp.json.return_value = LOOKUP if "lookup" in url else CHART
    return resp


class FeedKeyTest(TestCase):
    def test_ignores_scheme_www_case_and_trailing_slash(self):
        self.assertEqual(
            feed_key("http://www.Example.com/feed/"),
            feed_key("https://example.com/feed"),
        )

    def test_keeps_query(self):
        self.assertNotEqual(
            feed_key("https://example.com/feed?id=1"),
            feed_key("https://example.com/feed?id=2"),
        )


class ImportTopChartTest(TestCase):
    def setUp(self):
        Podcast.objects.create(name="Known Show", url="https://example.com/known")
        # Same show under a feed URL Apple no longer lists: matched by name.
        Podcast.objects.create(name="renamed feed", url="https://old.example.com/rss")

    @patch("audio_processing.tasks.podcast_tasks.import_podcast.delay")
    @patch("audio_processing.chart_import.requests.get", side_effect=fake_get)
    def test_adds_only_new_shows_without_processing(self, _get, delay):
        summary = import_top_chart()

        self.assertEqual(summary["created"], ["New Show"])
        self.assertEqual(summary["already_present"], 2)
        self.assertEqual(summary["no_public_feed"], ["Apple Exclusive"])

        podcast = Podcast.objects.get(url="https://feeds.example.com/new")
        self.assertFalse(podcast.auto_process)
        self.assertTrue(podcast.is_active)
        delay.assert_called_once_with(podcast.id, process_latest=0)

    @patch("audio_processing.tasks.podcast_tasks.import_podcast.delay")
    @patch("audio_processing.chart_import.requests.get", side_effect=fake_get)
    def test_second_run_adds_nothing(self, _get, delay):
        import_top_chart()
        summary = import_top_chart()
        self.assertEqual(summary["created"], [])
        self.assertEqual(delay.call_count, 1)


class CatalogEpisodesTestBase(TestCase):
    def setUp(self):
        cache.clear()
        self.podcast = Podcast.objects.create(
            name="Catalog Show", url="https://example.com/catalog"
        )
        self.summarized = Episode.objects.create(
            podcast=self.podcast,
            title="Summarized election episode",
            raw_audio_url="https://example.com/summarized.mp3",
            summary="## Overview\nA summary.",
        )
        self.transcribed = Episode.objects.create(
            podcast=self.podcast,
            title="Transcribed election episode",
            raw_audio_url="https://example.com/transcribed.mp3",
            transcript="Hello and welcome.",
        )
        self.notes_only = Episode.objects.create(
            podcast=self.podcast,
            title="Notes only episode",
            raw_audio_url="https://example.com/notes.mp3",
            description="<p>Show notes about the <b>election</b>.</p>",
            summary="",
        )


class HasContentTest(CatalogEpisodesTestBase):
    def test_has_content_q(self):
        ids = set(
            Episode.objects.filter(Episode.has_content_q()).values_list("id", flat=True)
        )
        self.assertEqual(ids, {self.summarized.id, self.transcribed.id})

    def test_episode_list_has_content_param(self):
        url = reverse("v1:api-v1-episodes-list")
        client = APIClient()

        all_titles = {e["title"] for e in client.get(url).json()["results"]}
        self.assertIn("Notes only episode", all_titles)

        filtered = client.get(url, {"has_content": "true"}).json()["results"]
        self.assertEqual(
            {e["title"] for e in filtered},
            {"Summarized election episode", "Transcribed election episode"},
        )


class SitemapTest(CatalogEpisodesTestBase):
    NS = "{http://www.sitemaps.org/schemas/sitemap/0.9}"

    def _locs(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200)
        root = ElementTree.fromstring(response.content)
        return [el.text for el in root.iter(f"{self.NS}loc")]

    def test_episode_sitemap_lists_only_episodes_with_content(self):
        locs = self._locs("/sitemap-episodes-1.xml")
        self.assertEqual(len(locs), 2)
        self.assertTrue(
            any(
                loc.endswith(f"/shows/{self.podcast.slug}/{self.summarized.slug}")
                for loc in locs
            )
        )
        self.assertFalse(any(self.notes_only.slug in loc for loc in locs))

    def test_podcast_sitemap_uses_shows_route(self):
        locs = self._locs("/sitemap-podcasts-1.xml")
        self.assertTrue(
            any(loc.endswith(f"/shows/{self.podcast.slug}") for loc in locs)
        )


class CatalogSearchTest(CatalogEpisodesTestBase):
    def test_new_feed_episodes_are_searchable_by_description(self):
        for episode in (self.summarized, self.transcribed, self.notes_only):
            episode.index_to_search()

        url = reverse("v1:api-v1-search")
        data = APIClient().get(url, {"q": "election", "type": "episode"}).json()
        titles = [e["title"] for e in data["episodes"]]

        self.assertIn("Notes only episode", titles)
        # Episodes with a summary or transcript rank first.
        self.assertEqual(titles[-1], "Notes only episode")

    def test_publisher_transcript_on_unprocessed_episode_is_searchable(self):
        from types import SimpleNamespace

        from audio_processing.transcript_manager import apply_publisher_transcript

        transcript = SimpleNamespace(
            text="We talk about zeppelins for an hour.",
            source="publisher:vtt",
            format="vtt",
            has_speakers=False,
        )
        apply_publisher_transcript(self.notes_only, transcript)

        url = reverse("v1:api-v1-search")
        data = APIClient().get(url, {"q": "zeppelins", "type": "episode"}).json()
        self.assertEqual([e["title"] for e in data["episodes"]], ["Notes only episode"])
