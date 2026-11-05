from datetime import datetime, timezone as dt_timezone
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from audio_processing.models import Episode, Podcast

IN_WINDOW = datetime(2026, 11, 5, 1, 0, tzinfo=dt_timezone.utc)
OUT_OF_WINDOW = datetime(2026, 11, 5, 3, 0, tzinfo=dt_timezone.utc)


class BackfillSummariesScriptsTest(TestCase):
    def setUp(self):
        self.podcast = Podcast.objects.create(name="Pod", url="https://pod.example/rss")

    def _episode(self, title, completed_at, summary="", script=""):
        return Episode.objects.create(
            title=title,
            podcast=self.podcast,
            raw_audio_url=f"https://example.com/{title}.mp3",
            transcript="hello world",
            summary=summary,
            script_transcript=script,
            processing_completed_at=completed_at,
        )

    def _run(self, *args):
        out = StringIO()
        call_command(
            "backfill_summaries_scripts",
            "--since=2026-11-05T00:00",
            "--until=2026-11-05T02:00",
            *args,
            stdout=out,
            stderr=StringIO(),
        )
        return out.getvalue()

    @patch.object(Episode, "index_to_search")
    @patch.object(Episode, "generate_summary", return_value="s")
    @patch.object(Episode, "generate_speaker_script", return_value="x")
    def test_regenerates_only_missing_steps_in_window(self, script, summary, index):
        self._episode("no-summary", IN_WINDOW, script="x")
        self._episode("no-script", IN_WINDOW, summary="s")
        self._episode("complete", IN_WINDOW, summary="s", script="x")
        self._episode("later", OUT_OF_WINDOW)

        out = self._run()

        self.assertIn("2 episode(s)", out)
        self.assertEqual(summary.call_count, 1)
        self.assertEqual(script.call_count, 1)
        self.assertEqual(index.call_count, 2)

    @patch.object(Episode, "generate_summary")
    @patch.object(Episode, "generate_speaker_script")
    def test_dry_run_changes_nothing(self, script, summary):
        self._episode("no-summary", IN_WINDOW, script="x")

        out = self._run("--dry-run")

        self.assertIn("no-summary", out)
        summary.assert_not_called()
        script.assert_not_called()

    @patch.object(Episode, "index_to_search")
    @patch.object(Episode, "generate_summary", return_value=None)
    def test_fails_when_step_still_fails(self, summary, index):
        self._episode("no-summary", IN_WINDOW, script="x")

        with self.assertRaises(CommandError):
            self._run()
        index.assert_not_called()

    def test_requires_a_filter(self):
        with self.assertRaises(CommandError):
            call_command("backfill_summaries_scripts")
