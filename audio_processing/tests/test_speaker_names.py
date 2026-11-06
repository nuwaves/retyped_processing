from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from audio_processing import speaker_names as sn
from audio_processing.models.mixins.groq_mixin import GroqMixin

TRANSCRIPT = (
    "Speaker 1: Welcome to the show, I'm John Coogan.\n\n"
    "Speaker 2: And I'm Jordi Hays.\n\n"
    "Speaker 1: Speaker 2 is my co-host: we talk tech.\n\n"
    "Unknown: [ad read]\n\n"
    "Speaker 3: Thanks for having me."
)


def episode(transcript=TRANSCRIPT, source="publisher:json"):
    podcast = SimpleNamespace(name="Tech Show", description="Tech news", summary="")
    return SimpleNamespace(
        id=1,
        title="Ep",
        description="With guest Ada Lovelace",
        podcast=podcast,
        transcript=transcript,
        transcript_source=source,
        get_groq_completion=MagicMock(),
    )


class StubConfigTestCase(SimpleTestCase):
    """name_speakers reads SPEAKER_MODEL; constance needs a database."""

    def setUp(self):
        stub = patch.object(sn, "config", SimpleNamespace(SPEAKER_MODEL="m"))
        stub.start()
        self.addCleanup(stub.stop)


class DetectTurnsTest(SimpleTestCase):
    def test_publisher_transcript_with_turns(self):
        self.assertTrue(sn.has_speaker_turns(episode()))

    def test_speech_to_text_and_unlabelled_text_need_full_rewrite(self):
        self.assertFalse(sn.has_speaker_turns(episode(source="")))
        self.assertFalse(
            sn.has_speaker_turns(episode(transcript="Just words here. More words."))
        )
        self.assertFalse(
            sn.has_speaker_turns(episode(transcript="Speaker 1: hi\n\nno label here"))
        )

    def test_samples_only_generic_labels_with_word_share(self):
        samples = sn.speaker_samples(sn.turns(TRANSCRIPT))
        self.assertEqual(set(samples), {"Speaker 1", "Speaker 2", "Speaker 3"})
        self.assertEqual(
            samples["Speaker 1"]["lines"][0],
            "Speaker 2 is my co-host: we talk tech.",
        )
        self.assertGreater(samples["Speaker 1"]["share"], samples["Speaker 2"]["share"])


class ApplyNamesTest(StubConfigTestCase):
    def test_only_turn_labels_are_renamed(self):
        script = sn.apply_names(
            TRANSCRIPT, {"Speaker 1": "John Coogan", "Speaker 2": "Jordi Hays"}
        )
        self.assertIn("John Coogan: Speaker 2 is my co-host: we talk tech.", script)
        self.assertIn("Jordi Hays: And I'm Jordi Hays.", script)
        self.assertIn("Speaker 3: Thanks", script)
        self.assertIn("Unknown: [ad read]", script)

    def test_parse_names_drops_nulls_unknown_labels_and_bad_names(self):
        content = (
            'Sure: {"Speaker 1": "John  Coogan", "Speaker 2": null, '
            '"Speaker 3": "Speaker 3", "Speaker 9": "Someone", '
            '"Speaker 4": "Host: Bob"}'
        )
        labels = ["Speaker 1", "Speaker 2", "Speaker 3", "Speaker 4"]
        self.assertEqual(sn.parse_names(content, labels), {"Speaker 1": "John Coogan"})
        self.assertEqual(
            sn.parse_names('{"Speaker 1": "null", "Speaker 2": "Unknown"}', labels),
            {},
        )
        self.assertIsNone(sn.parse_names("no json", labels))
        self.assertIsNone(sn.parse_names(None, labels))

    def test_names_must_appear_in_what_the_model_saw(self):
        content = '{"Speaker 1": "John Coogan", "Speaker 2": "Max Farrens"}'
        names = sn.parse_names(
            content, ["Speaker 1", "Speaker 2"], evidence="hosted by Coogan"
        )
        self.assertEqual(names, {"Speaker 1": "John Coogan"})

    def test_host_named_in_show_title_is_accepted(self):
        names = sn.parse_names(
            '{"Speaker 1": "Dwarkesh Patel"}',
            ["Speaker 1"],
            evidence="Episode with a historian",
            show_name="Dwarkesh Podcast",
        )
        self.assertEqual(names, {"Speaker 1": "Dwarkesh Patel"})

    def test_invented_name_is_left_generic(self):
        ep = episode()
        ep.get_groq_completion.return_value = (
            '{"Speaker 1": "John Coogan", "Speaker 3": "John Coogan", '
            '"Speaker 2": "Max Farrens"}'
        )
        script = sn.name_speakers(ep)
        self.assertIn("Speaker 2: And I'm Jordi Hays.", script)


class NameSpeakersTest(StubConfigTestCase):
    def test_maps_labels_with_one_short_request(self):
        ep = episode()
        ep.get_groq_completion.return_value = (
            '{"Speaker 1": "John Coogan", "Speaker 2": "Jordi Hays", '
            '"Speaker 3": "Ada Lovelace"}'
        )
        script = sn.name_speakers(ep)
        self.assertTrue(script.startswith("John Coogan: Welcome"))
        self.assertIn("Ada Lovelace: Thanks for having me.", script)
        kwargs = ep.get_groq_completion.call_args.kwargs
        self.assertEqual(kwargs["max_tokens"], sn.NAMES_MAX_TOKENS)
        self.assertIn("With guest Ada Lovelace", kwargs["prompt"])

    def test_unreadable_answer_returns_none(self):
        ep = episode()
        ep.get_groq_completion.return_value = None
        self.assertIsNone(sn.name_speakers(ep))

    def test_already_named_needs_no_request(self):
        named = "John Coogan: Hi.\n\nJordi Hays: Hey."
        ep = episode(transcript=named)
        self.assertEqual(sn.name_speakers(ep), named)
        ep.get_groq_completion.assert_not_called()


class ScriptStepTest(SimpleTestCase):
    def _episode(self, **kwargs):
        ep = GroqMixin()
        ep.raw_audio_url = "https://cdn.example/a.mp3"
        ep.id = 1
        ep.transcript = TRANSCRIPT
        ep.transcript_source = "publisher:json"
        ep.script_transcript = ""
        ep.save = MagicMock()
        for key, value in kwargs.items():
            setattr(ep, key, value)
        return ep

    def test_publisher_turns_skip_the_full_rewrite(self):
        ep = self._episode()
        with (
            patch(
                "audio_processing.models.mixins.groq_mixin.name_speakers",
                return_value="John Coogan: hi",
            ) as name,
            patch(
                "audio_processing.models.mixins.groq_mixin.get_speaker_transcript_prompt"
            ) as rewrite,
        ):
            self.assertEqual(ep.generate_speaker_script(), "John Coogan: hi")
        name.assert_called_once_with(ep)
        rewrite.assert_not_called()
        self.assertEqual(ep.script_transcript, "John Coogan: hi")
        ep.save.assert_called_once()

    def test_failed_naming_saves_nothing(self):
        ep = self._episode()
        with patch(
            "audio_processing.models.mixins.groq_mixin.name_speakers",
            return_value=None,
        ):
            self.assertIsNone(ep.generate_speaker_script())
        ep.save.assert_not_called()
