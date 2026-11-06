from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from audio_processing.models import Episode, Podcast

LONG = "word " * 10000  # 50,000 characters


class FixTruncatedScriptsTest(TestCase):
    def setUp(self):
        self.podcast = Podcast.objects.create(name="Pod", url="https://pod.example/rss")

    def _episode(self, title, transcript=LONG, script="Host: short", **extra):
        return Episode.objects.create(
            title=title,
            podcast=self.podcast,
            raw_audio_url=f"https://example.com/{title}.mp3",
            transcript=transcript,
            script_transcript=script,
            **extra,
        )

    def _run(self, *args):
        out = StringIO()
        call_command(
            "fix_truncated_scripts", "--workers=1", *args, stdout=out, stderr=out
        )
        return out.getvalue()

    def test_selects_only_cut_off_scripts_of_long_transcripts(self):
        self._episode("cut")
        self._episode("complete", script="x" * 45000)
        self._episode("short", transcript="word " * 100)
        self._episode("no-script", script="")
        self._episode("running", processing_status=Episode.ProcessingStatus.RUNNING)
        out = self._run("--dry-run")
        self.assertIn("1 cut-off script(s)", out)
        self.assertIn("- cut", out)

    @patch.object(Episode, "index_to_search")
    def test_rewrites_and_reindexes(self, index):
        episode = self._episode("cut")

        def regenerate(self):
            self.script_transcript = "Host: " + "word " * 9500
            self.save()
            return self.script_transcript

        with patch.object(Episode, "generate_speaker_script", regenerate):
            out = self._run()
        episode.refresh_from_db()
        self.assertGreater(len(episode.script_transcript), 40000)
        index.assert_called_once()
        self.assertIn("fixed 1, failed 0", out)
        # Fixed scripts aren't picked up again.
        self.assertIn("0 cut-off script(s)", self._run("--dry-run"))

    @patch.object(Episode, "index_to_search")
    @patch.object(Episode, "generate_speaker_script", return_value=None)
    def test_failure_keeps_old_script(self, script, index):
        episode = self._episode("cut")
        out = self._run()
        episode.refresh_from_db()
        self.assertEqual(episode.script_transcript, "Host: short")
        index.assert_not_called()
        self.assertIn("fixed 0, failed 1", out)
