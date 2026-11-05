from importlib import import_module
from unittest.mock import MagicMock, patch

import requests
from constance.models import Constance
from django.apps import apps
from django.test import SimpleTestCase, TestCase, override_settings

from audio_processing.models.mixins import groq_mixin, summarizable_mixin
from audio_processing.models.mixins.groq_mixin import GroqMixin, clean_speaker_labels
from audio_processing.models.mixins.summarizable_mixin import SummarizableMixin
from audio_processing.utils import llm

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


def _response(status=200, content="ok", headers=None):
    response = MagicMock()
    response.status_code = status
    response.headers = headers or {}
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    if status >= 400:
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=response
        )
    return response


@override_settings(
    LLM_API_URL="https://llm.example.com/v1/chat/completions",
    LLM_API_KEY="test-key",
    LLM_TIMEOUT=600,
)
class ChatCompletionRetryTest(SimpleTestCase):
    def setUp(self):
        sleep = patch.object(llm.time, "sleep")
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def test_retries_rate_limit_then_succeeds(self):
        responses = [
            _response(429, headers={"Retry-After": "7"}),
            _response(content="done"),
        ]
        with patch.object(llm.requests, "post", side_effect=responses) as post:
            self.assertEqual(llm.post_chat_completion({}), "done")
        self.assertEqual(post.call_count, 2)
        self.sleep.assert_called_once_with(7.0)

    def test_caps_long_retry_after(self):
        responses = [_response(503, headers={"Retry-After": "3600"}), _response()]
        with patch.object(llm.requests, "post", side_effect=responses):
            llm.post_chat_completion({})
        self.sleep.assert_called_once_with(llm.MAX_RETRY_AFTER)

    def test_retries_connection_error_and_empty_completion(self):
        responses = [
            requests.exceptions.ConnectionError("reset"),
            _response(content="  "),
            _response(content="done"),
        ]
        with patch.object(llm.requests, "post", side_effect=responses) as post:
            self.assertEqual(llm.post_chat_completion({}), "done")
        self.assertEqual(post.call_count, 3)

    def test_raises_after_last_attempt(self):
        with patch.object(
            llm.requests, "post", side_effect=lambda *a, **k: _response(500)
        ) as post:
            with self.assertRaises(requests.exceptions.HTTPError):
                llm.post_chat_completion({})
        self.assertEqual(post.call_count, llm.MAX_ATTEMPTS)

    def test_does_not_retry_client_errors_or_read_timeouts(self):
        for failure in (_response(400), requests.exceptions.ReadTimeout("slow")):
            with patch.object(llm.requests, "post", side_effect=[failure]) as post:
                with self.assertRaises(requests.exceptions.RequestException):
                    llm.post_chat_completion({})
            self.assertEqual(post.call_count, 1)
        self.sleep.assert_not_called()

    def test_summary_survives_one_transient_failure(self):
        class FakeEpisode(SummarizableMixin):
            transcript = "words " * 50
            description = ""
            podcast = None
            summary = None
            save = MagicMock()

        episode = FakeEpisode()
        responses = [_response(502), _response(content="## Summary\nGood.")]
        # constance reads the model from the database, which SimpleTestCase blocks.
        model_config = MagicMock(SUMMARY_MODEL="summary-model")
        with (
            patch.object(summarizable_mixin, "config", model_config),
            patch.object(llm.requests, "post", side_effect=responses),
        ):
            self.assertEqual(episode.generate_summary(), "## Summary\nGood.")
        self.assertEqual(episode.summary, "## Summary\nGood.")
