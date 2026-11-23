"""
R2: an RSS feed must not overwrite another podcast's episode.

Episode.raw_audio_url is globally unique, and create_from_entry falls back to
matching on it. That fallback must only ever return an episode of the podcast
whose feed is being processed.
"""

from datetime import UTC, datetime
from datetime import timezone as dt_timezone
from unittest.mock import Mock

from django.test import TestCase

from audio_processing.models import Episode, Podcast

AUDIO_URL = "https://cdn.example.com/a/episode-1.mp3"


def make_entry(title, audio_url=AUDIO_URL, summary="Attacker description"):
    entry = Mock()
    entry.get = lambda key, default=None: {"title": title}.get(key, default)
    enclosure = Mock()
    enclosure.get = lambda key, default=None: {
        "type": "audio/mpeg",
        "href": audio_url,
        "length": "999",
    }.get(key, default)
    entry.enclosures = [enclosure]
    entry.summary = summary
    entry.subtitle = "Attacker subtitle"
    entry.itunes_subtitle = "Attacker subtitle"
    entry.image = None
    entry.published_parsed = (2030, 1, 1, 0, 0, 0, 1, 1, 0)
    content = Mock()
    content.get = Mock(return_value="content")
    entry.content = [content]
    entry.links = []
    entry.itunes_episode = None
    entry.itunes_season = None
    entry.itunes_episodetype = None
    entry.itunes_explicit = None
    entry.itunes_keywords = None
    entry.itunes_duration = None
    entry.tags = []
    return entry


class FeedCannotOverwriteOtherPodcastEpisodeTest(TestCase):
    def setUp(self):
        self.podcast_a = Podcast.objects.create(
            name="Podcast A", url="https://a.example.com/feed.xml"
        )
        self.podcast_b = Podcast.objects.create(
            name="Podcast B", url="https://b.example.com/feed.xml"
        )
        self.release = datetime(2024, 5, 1, tzinfo=UTC)
        self.episode_a = Episode.objects.create(
            podcast=self.podcast_a,
            title="A original title",
            raw_audio_url=AUDIO_URL,
            description="A original description",
            release_date=self.release,
            pub_date=self.release,
        )
        self.episode_a.refresh_from_db()
        self.original_links = self.episode_a.transcript_links

    def test_other_feed_with_same_audio_url_changes_nothing(self):
        links = {AUDIO_URL: [{"url": "https://evil.example.com/t.vtt"}]}
        before = Episode.objects.count()

        result = Episode.create_from_entry(
            self.podcast_b, make_entry("Hijacked title"), links
        )

        self.assertIsNone(result)
        self.assertEqual(Episode.objects.count(), before)
        self.episode_a.refresh_from_db()
        self.assertEqual(self.episode_a.podcast_id, self.podcast_a.id)
        self.assertEqual(self.episode_a.title, "A original title")
        self.assertEqual(self.episode_a.description, "A original description")
        self.assertEqual(self.episode_a.release_date, self.release)
        self.assertEqual(self.episode_a.transcript_links, self.original_links)
        self.assertFalse(Episode.objects.filter(podcast=self.podcast_b).exists())

    def test_own_feed_still_updates_by_audio_url(self):
        result = Episode.create_from_entry(
            self.podcast_a, make_entry("A renamed title", summary="A new description")
        )

        self.assertIsNotNone(result)
        self.assertEqual(result.pk, self.episode_a.pk)
        self.episode_a.refresh_from_db()
        self.assertEqual(self.episode_a.title, "A renamed title")
        self.assertEqual(self.episode_a.description, "A new description")

    def test_own_feed_title_match_still_updates(self):
        result = Episode.create_from_entry(
            self.podcast_a,
            make_entry("A original title", summary="Refreshed description"),
        )

        self.assertEqual(result.pk, self.episode_a.pk)
        self.episode_a.refresh_from_db()
        self.assertEqual(self.episode_a.description, "Refreshed description")

    def test_orphaned_episode_is_not_adopted(self):
        """Documented behavior: an episode with podcast=None is left alone."""
        orphan_url = "https://cdn.example.com/orphan.mp3"
        orphan = Episode.objects.create(
            podcast=None, title="Orphan", raw_audio_url=orphan_url
        )

        result = Episode.create_from_entry(
            self.podcast_b, make_entry("Claiming orphan", audio_url=orphan_url)
        )

        self.assertIsNone(result)
        orphan.refresh_from_db()
        self.assertIsNone(orphan.podcast_id)
        self.assertEqual(orphan.title, "Orphan")

    def test_process_feed_counts_skipped_entry_as_failed(self):
        feed = Mock()
        feed.entries = [make_entry("Hijacked title")]
        feed.transcript_links = None
        self.podcast_b.fetch_feed = Mock(return_value=feed)

        result = self.podcast_b.process_feed()

        self.assertEqual(result.get("failed"), 1)

        self.episode_a.refresh_from_db()
        self.assertEqual(self.episode_a.title, "A original title")
        self.assertEqual(self.episode_a.podcast_id, self.podcast_a.id)

    def test_query_string_variant_of_other_podcast_url_is_skipped(self):
        result = Episode.create_from_entry(
            self.podcast_b,
            make_entry("Hijacked title", audio_url=AUDIO_URL + "?utm=x"),
        )

        self.assertIsNone(result)
        self.episode_a.refresh_from_db()
        self.assertEqual(self.episode_a.title, "A original title")
        self.assertFalse(Episode.objects.filter(podcast=self.podcast_b).exists())
