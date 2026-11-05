"""Tests for transcribing queued episodes through Groq batch jobs."""

import json
from unittest.mock import Mock, patch

from constance.test import override_config
from django.test import TestCase, override_settings
from django.utils import timezone

from audio_processing.models import Episode, Podcast, ProcessingBatch

Status = Episode.ProcessingStatus
DELAY = "audio_processing.tasks.episode_tasks.process_complete_workflow.delay"
POST = "audio_processing.models.processing_batch.requests.post"
GET = "audio_processing.models.processing_batch.requests.get"


def _response(payload=None, lines=()):
    response = Mock()
    response.raise_for_status = Mock()
    response.json.return_value = payload or {}
    response.iter_lines.return_value = [
        json.dumps(line).encode("utf-8") for line in lines
    ]
    return response


def _success(episode, text):
    return {
        "custom_id": f"episode-{episode.id}",
        "response": {"status_code": 200, "body": {"text": text}},
        "error": None,
    }


def _failure(episode):
    return {
        "custom_id": f"episode-{episode.id}",
        "response": {"status_code": 400, "body": {"error": {"message": "too big"}}},
        "error": None,
    }


@override_settings(GROQ_API_KEY="test-key")
class BatchTranscriptionTest(TestCase):
    def setUp(self):
        self.podcast = Podcast.objects.create(
            name="Show", url="https://show.example/rss"
        )

    def episode(self, title="ep", **kwargs):
        return Episode.objects.create(
            title=title,
            podcast=self.podcast,
            raw_audio_url=f"https://show.example/{title}.mp3",
            release_date=timezone.now(),
            **kwargs,
        )

    def submitted_batch(self, *episodes):
        Episode.objects.filter(pk__in=[e.pk for e in episodes]).update(
            processing_status=Status.QUEUED,
            processing_step=Episode.BATCH_SUBMITTED_STEP,
        )
        return ProcessingBatch.objects.create(
            external_batch_id="batch_1",
            record_count=len(episodes),
            episode_ids=[e.pk for e in episodes],
        )

    # Queueing

    @patch(DELAY)
    def test_queue_waits_for_batch_by_default(self, mock_delay):
        episode = self.episode()

        self.assertTrue(episode.queue_processing())

        mock_delay.assert_not_called()
        episode.refresh_from_db()
        self.assertEqual(episode.processing_status, Status.QUEUED)
        self.assertEqual(episode.processing_step, Episode.BATCH_PENDING_STEP)

    @patch(DELAY)
    def test_episode_with_transcript_skips_batch(self, mock_delay):
        episode = self.episode(transcript="already done")

        episode.queue_processing()

        mock_delay.assert_called_once_with(episode.id)
        episode.refresh_from_db()
        self.assertEqual(episode.processing_step, "")

    @patch(DELAY)
    def test_realtime_argument_skips_batch(self, mock_delay):
        episode = self.episode()

        episode.queue_processing(realtime=True)

        mock_delay.assert_called_once_with(episode.id)

    @override_config(TRANSCRIPTION_MODE="realtime")
    @patch(DELAY)
    def test_realtime_mode_skips_batch(self, mock_delay):
        episode = self.episode()

        episode.queue_processing()

        mock_delay.assert_called_once_with(episode.id)

    # Submitting

    @patch(POST)
    def test_submits_waiting_episodes_in_one_batch(self, mock_post):
        mock_post.side_effect = [
            _response({"id": "file_1"}),
            _response({"id": "batch_1"}),
        ]
        first, second = self.episode("a"), self.episode("b")
        first.queue_processing()
        second.queue_processing()
        not_waiting = self.episode("idle")

        batches = ProcessingBatch.submit_pending_transcriptions()

        self.assertEqual(len(batches), 1)
        batch = batches[0]
        self.assertEqual(batch.external_batch_id, "batch_1")
        self.assertEqual(sorted(batch.episode_ids), sorted([first.pk, second.pk]))

        upload_call, create_call = mock_post.call_args_list
        _, content = upload_call.kwargs["files"]["file"]
        lines = [json.loads(line) for line in content.decode().splitlines()]
        self.assertEqual(
            {line["custom_id"] for line in lines},
            {f"episode-{first.pk}", f"episode-{second.pk}"},
        )
        self.assertEqual(lines[0]["url"], "/v1/audio/transcriptions")
        self.assertEqual(
            create_call.kwargs["json"],
            {
                "input_file_id": "file_1",
                "endpoint": "/v1/audio/transcriptions",
                "completion_window": "24h",
            },
        )

        for episode in (first, second):
            episode.refresh_from_db()
            self.assertEqual(episode.processing_step, Episode.BATCH_SUBMITTED_STEP)
        not_waiting.refresh_from_db()
        self.assertEqual(not_waiting.processing_step, "")

    @patch(POST)
    def test_nothing_waiting_submits_nothing(self, mock_post):
        self.assertEqual(ProcessingBatch.submit_pending_transcriptions(), [])
        mock_post.assert_not_called()

    # Results

    @patch(DELAY)
    @patch(GET)
    def test_completed_batch_saves_transcripts_and_resumes(self, mock_get, mock_delay):
        ok, failed = self.episode("ok"), self.episode("failed")
        batch = self.submitted_batch(ok, failed)
        mock_get.side_effect = [
            _response({"status": "completed", "output_file_id": "file_out"}),
            _response(lines=[_success(ok, "hello world"), _failure(failed)]),
        ]

        result = batch.fetch_and_apply_groq_results()

        self.assertEqual(result["updated"], 1)
        self.assertEqual(result["resumed"], 2)
        ok.refresh_from_db()
        failed.refresh_from_db()
        self.assertEqual(ok.transcript, "hello world")
        self.assertFalse(failed.transcript)
        # Both continue: the failed one is transcribed directly by its workflow.
        self.assertEqual(
            sorted(c.args[0] for c in mock_delay.call_args_list),
            sorted([ok.pk, failed.pk]),
        )
        self.assertEqual(ok.processing_step, "")
        self.assertEqual(failed.processing_status, Status.QUEUED)
        batch.refresh_from_db()
        self.assertEqual(batch.processing_state, ProcessingBatch.STATE_SUCCESSFUL)
        self.assertEqual(batch.error, "1 requests failed")

    @patch(DELAY)
    @patch(GET)
    def test_expired_batch_falls_back_to_direct_transcription(
        self, mock_get, mock_delay
    ):
        episode = self.episode()
        batch = self.submitted_batch(episode)
        mock_get.return_value = _response({"status": "expired"})

        batch.fetch_and_apply_groq_results()

        mock_delay.assert_called_once_with(episode.pk)
        batch.refresh_from_db()
        self.assertEqual(batch.processing_state, ProcessingBatch.STATE_ERRORED)

    @patch(DELAY)
    @patch(GET)
    def test_unfinished_batch_changes_nothing(self, mock_get, mock_delay):
        episode = self.episode()
        batch = self.submitted_batch(episode)
        mock_get.return_value = _response({"status": "in_progress"})

        batch.fetch_and_apply_groq_results()

        mock_delay.assert_not_called()
        episode.refresh_from_db()
        self.assertEqual(episode.processing_step, Episode.BATCH_SUBMITTED_STEP)
        batch.refresh_from_db()
        self.assertEqual(batch.processing_state, ProcessingBatch.STATE_CREATED)

    @patch(DELAY)
    @patch(GET)
    def test_episode_no_longer_waiting_is_not_resumed(self, mock_get, mock_delay):
        episode = self.episode()
        batch = self.submitted_batch(episode)
        # Re-queued for realtime processing while the batch was running.
        Episode.objects.filter(pk=episode.pk).update(processing_step="")
        mock_get.side_effect = [
            _response({"status": "completed", "output_file_id": "file_out"}),
            _response(lines=[_success(episode, "text")]),
        ]

        batch.fetch_and_apply_groq_results()

        mock_delay.assert_not_called()
        episode.refresh_from_db()
        self.assertEqual(episode.transcript, "text")
