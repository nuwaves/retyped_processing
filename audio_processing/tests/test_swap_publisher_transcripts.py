from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from audio_processing import transcript_manager as tm
from audio_processing.models import Episode, Podcast

COMMAND = "audio_processing.management.commands.swap_publisher_transcripts"
LINKS = [{"url": "https://t.example/a.json", "type": "application/json"}]


def publisher(has_speakers=True):
    text = "Speaker 1: " + "word " * 300 + "\n\nSpeaker 2: hi there"
    return tm.PublisherTranscript(text, "json", "u", has_speakers, 9.5, 303)


class SwapPublisherTranscriptsTest(TestCase):
    def setUp(self):
        self.podcast = Podcast.objects.create(name="Pod", url="https://pod.example/rss")
        refresh = patch.object(Podcast, "refresh_transcript_links", return_value=0)
        refresh.start()
        self.addCleanup(refresh.stop)
        index = patch.object(Episode, "index_to_search")
        self.index = index.start()
        self.addCleanup(index.stop)

    def _episode(self, title, **extra):
        defaults = {
            "transcript": "whisper words",
            "script_transcript": "Host: whisper words",
            "transcript_links": LINKS,
        }
        defaults.update(extra)
        return Episode.objects.create(
            title=title,
            podcast=self.podcast,
            raw_audio_url=f"https://cdn.example/{title}.mp3",
            release_date=timezone.now(),
            duration=timedelta(seconds=10),
            **defaults,
        )

    def _run(self, *args):
        out = StringIO()
        call_command("swap_publisher_transcripts", *args, stdout=out, stderr=out)
        return out.getvalue()

    def test_swaps_transcript_and_renames_script(self):
        episode = self._episode("e")
        with (
            patch(f"{COMMAND}.best_publisher_transcript", return_value=publisher()),
            patch.object(
                Episode, "generate_speaker_script", return_value="A: hi"
            ) as script,
        ):
            out = self._run()
        episode.refresh_from_db()
        self.assertEqual(episode.transcript_source, "publisher:json")
        self.assertTrue(episode.transcript.startswith("Speaker 1: word"))
        script.assert_called_once()
        self.index.assert_called_once()
        self.assertIn("swapped 1", out)

    def test_without_speakers_keeps_the_old_script(self):
        episode = self._episode("e")
        with (
            patch(
                f"{COMMAND}.best_publisher_transcript",
                return_value=publisher(has_speakers=False),
            ),
            patch.object(Episode, "generate_speaker_script") as script,
        ):
            self._run()
        script.assert_not_called()
        episode.refresh_from_db()
        self.assertEqual(episode.script_transcript, "Host: whisper words")

    def test_dry_run_changes_nothing(self):
        episode = self._episode("e")
        with patch(f"{COMMAND}.best_publisher_transcript", return_value=publisher()):
            out = self._run("--dry-run")
        episode.refresh_from_db()
        self.assertEqual(episode.transcript, "whisper words")
        self.assertEqual(episode.transcript_source, "")
        self.index.assert_not_called()
        self.assertIn("would swap 1", out)

    def test_skips_publisher_and_linkless_episodes_and_marks_unusable(self):
        self._episode("done", transcript_source="publisher:vtt")
        self._episode("nolinks", transcript_links=[])
        unusable = self._episode("bad")
        with patch(f"{COMMAND}.best_publisher_transcript", return_value=None) as best:
            self._run()
            self._run()
        best.assert_called_once()
        unusable.refresh_from_db()
        self.assertIsNotNone(unusable.publisher_transcript_checked_at)
        self.assertEqual(unusable.transcript, "whisper words")
