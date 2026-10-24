from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from audio_processing.models import Episode, Podcast
from audio_processing.tasks.episode_tasks import (
    process_recent_episodes_without_transcript,
)


class ProcessRecentEpisodesWithoutTranscriptTest(TestCase):
    def setUp(self):
        self.active = Podcast.objects.create(
            name="Active", url="https://active.example/rss"
        )
        self.paused = Podcast.objects.create(
            name="Paused", url="https://paused.example/rss", is_active=False
        )

    def _episode(self, podcast, title):
        return Episode.objects.create(
            title=title,
            podcast=podcast,
            raw_audio_url=f"https://example.com/{title}.mp3",
            release_date=timezone.now(),
        )

    @patch("audio_processing.tasks.episode_tasks.process_complete_workflow.delay")
    def test_skips_episodes_from_paused_podcasts(self, mock_delay):
        mock_delay.return_value = Mock(id="task-id")
        active_episode = self._episode(self.active, "active")
        self._episode(self.paused, "paused")

        results = process_recent_episodes_without_transcript()

        mock_delay.assert_called_once_with(active_episode.id)
        self.assertEqual([r["episode_id"] for r in results], [active_episode.id])
