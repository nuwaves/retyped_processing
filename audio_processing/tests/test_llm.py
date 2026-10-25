from importlib import import_module
from unittest.mock import MagicMock, patch

from constance.models import Constance
from django.apps import apps
from django.test import SimpleTestCase, TestCase, override_settings

from audio_processing.models.mixins import groq_mixin
from audio_processing.models.mixins.groq_mixin import GroqMixin, clean_speaker_labels

clear_retired_chat_models = import_module(
    "audio_processing.migrations.0029_clear_retired_chat_models"
).clear_retired_chat_models


class ChatCompletionTest(TestCase):
    @override_settings(
        LLM_API_URL="https://llm.example.com/v1/chat/completions",
        LLM_API_KEY="test-key",
        LLM_TIMEOUT=600,
    )
    def test_posts_to_configured_provider_with_default_model(self):
        response = MagicMock()
        response.json.return_value = {"choices": [{"message": {"content": " hi "}}]}
        with patch.object(groq_mixin.requests, "post", return_value=response) as post:
            self.assertEqual(GroqMixin().get_groq_completion("hello"), "hi")
        url = post.call_args.args[0]
        kwargs = post.call_args.kwargs
        self.assertEqual(url, "https://llm.example.com/v1/chat/completions")
        self.assertEqual(kwargs["headers"]["Authorization"], "Bearer test-key")
        self.assertEqual(kwargs["json"]["model"], "deepseek-ai/DeepSeek-V4-Flash")
        self.assertEqual(kwargs["timeout"], 600)

    @override_settings(LLM_API_KEY="")
    def test_returns_none_without_api_key(self):
        with patch.object(groq_mixin.requests, "post") as post:
            self.assertIsNone(GroqMixin().get_groq_completion("hello"))
        post.assert_not_called()


class CleanSpeakerLabelsTest(SimpleTestCase):
    def test_strips_bold_from_speaker_labels(self):
        script = "**Paul Alex:** Welcome back.\n\n**Cassie**: Thanks, Paul."
        self.assertEqual(
            clean_speaker_labels(script),
            "Paul Alex: Welcome back.\n\nCassie: Thanks, Paul.",
        )

    def test_leaves_bold_inside_text_alone(self):
        script = "Paul Alex: That was **huge** for us."
        self.assertEqual(clean_speaker_labels(script), script)


class ClearRetiredChatModelsTest(TestCase):
    def test_deletes_only_rows_naming_retired_models(self):
        retired = '{"__type__": "default", "__value__": "llama-3.1-8b-instant"}'
        chosen = '{"__type__": "default", "__value__": "some/other-model"}'
        Constance.objects.create(key="SUMMARY_MODEL", value=retired)
        Constance.objects.create(key="TAG_MODEL", value=chosen)
        Constance.objects.create(key="TEXT_TO_SPEECH_MODEL", value=retired)

        clear_retired_chat_models(apps, None)

        self.assertEqual(
            set(Constance.objects.values_list("key", flat=True)),
            {"TAG_MODEL", "TEXT_TO_SPEECH_MODEL"},
        )
