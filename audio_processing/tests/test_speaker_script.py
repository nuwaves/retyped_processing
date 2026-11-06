from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from audio_processing.models import Episode, Podcast
from audio_processing.models.mixins import groq_mixin
from audio_processing.models.mixins.groq_mixin import speaker_labels, split_transcript
from audio_processing.prompts import get_speaker_transcript_prompt


class SplitTranscriptTest(SimpleTestCase):
    def test_short_transcript_is_one_part(self):
        self.assertEqual(split_transcript("Hello there.", max_chars=100), ["Hello there."])

    def test_parts_fit_and_keep_all_text(self):
        sentence = "This is a sentence about startups. "
        transcript = sentence * 300
        parts = split_transcript(transcript, max_chars=1000)
        self.assertGreater(len(parts), 1)
        self.assertTrue(all(len(p) <= 1000 for p in parts))
        self.assertTrue(all(p.endswith(".") for p in parts))
        self.assertEqual(" ".join(parts), transcript.strip())

    def test_prefers_paragraph_breaks(self):
        transcript = "a" * 700 + ".\n\n" + "b" * 200 + ". " + "c" * 500
        parts = split_transcript(transcript, max_chars=1000)
        self.assertEqual(parts[0], "a" * 700 + ".")

    def test_hard_split_without_whitespace(self):
        parts = split_transcript("x" * 2500, max_chars=1000)
        self.assertEqual([len(p) for p in parts], [1000, 1000, 500])


class SpeakerLabelsTest(SimpleTestCase):
    def test_labels_in_first_seen_order(self):
        script = "John Coogan: Hi.\n\nJordi Hays: Hey.\n\nJohn Coogan: So.\n[Laughter]"
        self.assertEqual(speaker_labels(script), ["John Coogan", "Jordi Hays"])


class SpeakerScriptTest(TestCase):
    def setUp(self):
        podcast = Podcast.objects.create(name="Pod", url="https://pod.example/rss")
        self.episode = Episode.objects.create(
            title="Long one",
            podcast=podcast,
            raw_audio_url="https://example.com/long.mp3",
            transcript="First sentence here. " * 20,
        )

    def test_single_part_prompt_is_unchanged(self):
        prompt = get_speaker_transcript_prompt(self.episode)
        self.assertNotIn("part 1 of", prompt)
        self.assertIn(self.episode.transcript, prompt)

    def test_formats_long_transcripts_in_parts(self):
        replies = ["Host: First part.\n\nGuest: Yes.", "**Host:** Second part."]
        with patch.object(groq_mixin, "split_transcript", return_value=["one", "two"]), \
                patch.object(Episode, "get_groq_completion", side_effect=replies) as llm:
            script = self.episode.generate_speaker_script()

        self.assertEqual(
            script, "Host: First part.\n\nGuest: Yes.\n\nHost: Second part."
        )
        self.episode.refresh_from_db()
        self.assertEqual(self.episode.script_transcript, script)
        second_prompt = llm.call_args_list[1].kwargs["prompt"]
        self.assertIn("part 2 of 2", second_prompt)
        self.assertIn("Host, Guest", second_prompt)
        self.assertIn("Guest: Yes.", second_prompt)

    def test_failed_part_saves_nothing(self):
        with patch.object(groq_mixin, "split_transcript", return_value=["one", "two"]), \
                patch.object(Episode, "get_groq_completion", side_effect=["Host: Hi.", None]):
            self.assertIsNone(self.episode.generate_speaker_script())

        self.episode.refresh_from_db()
        self.assertFalse(self.episode.script_transcript)
