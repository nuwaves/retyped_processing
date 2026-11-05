"""Tests for episode processing status tracking, podcast auto-process and the admin dashboard pages."""

from datetime import timedelta
from unittest.mock import Mock, patch

from constance.test import override_config
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from audio_processing.models import Episode, Podcast
from audio_processing.tasks.episode_tasks import (
    process_complete_workflow as process_complete_workflow_task,
)
from audio_processing.tasks.podcast_tasks import import_podcast

Status = Episode.ProcessingStatus
DELAY = "audio_processing.tasks.episode_tasks.process_complete_workflow.delay"
INDEX = (
    "audio_processing.models.mixins.searchable_mixin.SearchableMixin.index_to_search"
)


# These tests cover queueing itself, so transcribe right away rather than via a
# Groq batch (see test_batch_transcription.py).
@override_config(TRANSCRIPTION_MODE="realtime")
@patch(INDEX, Mock(return_value=None))
class StatusTestCase(TestCase):
    def setUp(self):
        self.podcast = Podcast.objects.create(
            name="Show", url="https://show.example/rss", is_active=True
        )

    def episode(self, title="ep", days_ago=0, **kwargs):
        return Episode.objects.create(
            title=title,
            podcast=self.podcast,
            raw_audio_url=f"https://show.example/{title}.mp3",
            release_date=timezone.now() - timedelta(days=days_ago),
            **kwargs,
        )


class QueueProcessingTest(StatusTestCase):
    @patch(DELAY)
    def test_queues_and_marks_queued(self, mock_delay):
        episode = self.episode(error="old error")

        self.assertTrue(episode.queue_processing())

        mock_delay.assert_called_once_with(episode.id)
        episode.refresh_from_db()
        self.assertEqual(episode.processing_status, Status.QUEUED)
        self.assertIsNotNone(episode.processing_queued_at)
        self.assertIsNone(episode.error)

    @patch(DELAY)
    def test_does_not_double_queue(self, mock_delay):
        for status in (Status.QUEUED, Status.RUNNING):
            episode = self.episode(
                title=status,
                processing_status=status,
                processing_started_at=timezone.now(),
            )
            self.assertFalse(episode.queue_processing())
        mock_delay.assert_not_called()

    @patch(DELAY)
    def test_requeues_stalled_run(self, mock_delay):
        started = timezone.now() - timedelta(
            seconds=settings.CELERY_TASK_TIME_LIMIT + 60
        )
        episode = self.episode(
            processing_status=Status.RUNNING, processing_started_at=started
        )
        self.assertTrue(episode.is_stalled)

        self.assertTrue(episode.queue_processing())
        mock_delay.assert_called_once_with(episode.id)


class WorkflowStatusTest(StatusTestCase):
    def _patch_steps(self, episode, **overrides):
        steps = {
            "upload_audio_to_s3": "s3://bucket/key",
            "generate_transcript": "transcript",
            "suggest_and_apply_tags": ["tag"],
            "generate_speaker_script": "script",
            "generate_summary": "summary",
            "extract_entities": ["entity"],
            "extract_quotes": ["quote"],
        }
        steps.update(overrides)
        for name, value in steps.items():
            setattr(episode, name, Mock(return_value=value))

    @patch("audio_processing.models.topic.Topic.set_episode_topics", return_value=True)
    def test_success_marks_done(self, _topics):
        episode = self.episode()
        self._patch_steps(episode)

        episode.process_complete_workflow()

        episode.refresh_from_db()
        self.assertEqual(episode.processing_status, Status.DONE)
        self.assertEqual(episode.processing_step, "")
        self.assertIsNotNone(episode.processing_started_at)
        self.assertIsNotNone(episode.processing_completed_at)
        self.assertIsNone(episode.error)

    @patch("audio_processing.models.topic.Topic.set_episode_topics", return_value=True)
    def test_non_fatal_step_errors_are_recorded(self, _topics):
        episode = self.episode()
        self._patch_steps(episode, generate_summary=None)

        episode.process_complete_workflow()

        episode.refresh_from_db()
        self.assertEqual(episode.processing_status, Status.DONE)
        self.assertIn("Failed to generate episode summary", episode.error)

    def test_s3_failure_marks_failed(self):
        episode = self.episode()
        self._patch_steps(episode, upload_audio_to_s3=None)

        episode.process_complete_workflow()

        episode.refresh_from_db()
        self.assertEqual(episode.processing_status, Status.FAILED)
        self.assertEqual(episode.processing_step, "s3")
        self.assertEqual(episode.error, "Failed to save audio to S3")
        self.assertIsNone(episode.processing_completed_at)

    def test_transcript_failure_marks_failed(self):
        episode = self.episode(s3_audio_url="s3://bucket/key")
        self._patch_steps(episode, generate_transcript=None)

        episode.process_complete_workflow()

        episode.refresh_from_db()
        self.assertEqual(episode.processing_status, Status.FAILED)
        self.assertEqual(episode.processing_step, "transcript")
        self.assertEqual(episode.error, "Failed to generate transcript")

    def test_task_exception_marks_failed(self):
        episode = self.episode()
        with patch.object(
            Episode, "process_complete_workflow", side_effect=RuntimeError("boom")
        ):
            result = process_complete_workflow_task(episode.id)

        self.assertFalse(result["success"])
        episode.refresh_from_db()
        self.assertEqual(episode.processing_status, Status.FAILED)
        self.assertIn("boom", episode.error)


class _Entry(dict):
    """Minimal stand-in for feedparser's entries: dict with attribute access."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name) from None


def _feed(*titles):
    """A parsed feed whose entries are newest-first, one day apart."""
    entries = [
        _Entry(
            title=title,
            enclosures=[
                {"type": "audio/mpeg", "href": f"https://show.example/{title}.mp3"}
            ],
            published_parsed=(timezone.now() - timedelta(days=i)).timetuple(),
        )
        for i, title in enumerate(titles)
    ]
    return _Entry(entries=entries, feed=_Entry())


class AutoProcessTest(StatusTestCase):
    def _process(self, *titles):
        with patch.object(Podcast, "fetch_feed", return_value=_feed(*titles)):
            return self.podcast.process_feed()

    @patch(DELAY)
    def test_off_by_default_queues_nothing(self, mock_delay):
        summary = self._process("a", "b")

        self.assertEqual(summary["created"], 2)
        self.assertEqual(summary["auto_queued"], 0)
        mock_delay.assert_not_called()

    @patch(DELAY)
    def test_queues_only_newest_new_episodes(self, mock_delay):
        self.podcast.auto_process = True
        self.podcast.auto_process_count = 2
        self.podcast.save()

        summary = self._process("newest", "middle", "oldest")

        self.assertEqual(summary["auto_queued"], 2)
        queued = set(
            Episode.objects.filter(processing_status=Status.QUEUED).values_list(
                "title", flat=True
            )
        )
        self.assertEqual(queued, {"newest", "middle"})

    @patch(DELAY)
    def test_existing_episodes_are_not_auto_queued(self, mock_delay):
        self._process("old")
        self.podcast.auto_process = True
        self.podcast.save()

        summary = self._process("new", "old")

        self.assertEqual(summary["created"], 1)
        self.assertEqual(summary["existing"], 1)
        self.assertEqual(
            list(
                Episode.objects.filter(processing_status=Status.QUEUED).values_list(
                    "title", flat=True
                )
            ),
            ["new"],
        )

    @patch(DELAY)
    def test_import_podcast_queues_latest(self, mock_delay):
        with patch.object(Podcast, "fetch_feed", return_value=_feed("a", "b", "c")):
            summary = import_podcast(self.podcast.id, process_latest=2)

        self.assertEqual(summary["queued"], 2)
        self.assertEqual(mock_delay.call_count, 2)


@override_settings(
    STORAGES={
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        }
    }
)
class AdminPagesTest(StatusTestCase):
    def setUp(self):
        super().setUp()
        self.admin = get_user_model().objects.create_superuser(
            "boss", "boss@example.com", "pw"
        )
        self.client.force_login(self.admin)

    def test_pages_render_for_staff(self):
        self.episode("new")
        self.episode("failed", processing_status=Status.FAILED, error="nope")
        urls = [
            reverse("admin:index"),
            reverse("admin:podcast_add_feed"),
            reverse("admin:processing_queue"),
            reverse("admin:processing_queue") + "?tab=failed",
            reverse("admin:podcast_episodes", args=[self.podcast.pk]),
            reverse("admin:audio_processing_episode_changelist"),
            reverse("admin:audio_processing_podcast_changelist"),
            reverse("admin:audio_processing_podcast_change", args=[self.podcast.pk]),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_partials_render(self):
        for url in (
            reverse("admin:processing_queue"),
            reverse("admin:podcast_episodes", args=[self.podcast.pk]),
        ):
            response = self.client.get(url, headers={"X-Partial": "1"})
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, "<html")

    def test_dashboard_lists_new_unprocessed(self):
        self.episode("fresh-one")
        self.episode("ancient", days_ago=30)

        response = self.client.get(reverse("admin:index"))

        self.assertContains(response, "fresh-one")
        self.assertNotContains(response, "ancient")

    def test_anonymous_redirected_to_login(self):
        self.client.logout()
        response = self.client.get(reverse("admin:processing_queue"))
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("admin:login"), response["Location"])

    @patch(DELAY)
    def test_retry_failed_requeues(self, mock_delay):
        failed = self.episode(processing_status=Status.FAILED, error="nope")

        response = self.client.post(
            reverse("admin:queue_episodes"), {"episode_ids": [failed.pk]}
        )

        self.assertEqual(response.status_code, 302)
        mock_delay.assert_called_once_with(failed.pk)
        failed.refresh_from_db()
        self.assertEqual(failed.processing_status, Status.QUEUED)

    @patch(DELAY)
    def test_retry_all_failed(self, mock_delay):
        self.episode("f1", processing_status=Status.FAILED)
        self.episode("f2", processing_status=Status.FAILED)
        self.episode("ok", processing_status=Status.DONE)

        self.client.post(reverse("admin:queue_episodes"), {"scope": "all_failed"})

        self.assertEqual(mock_delay.call_count, 2)

    def test_next_param_rejects_external_redirect(self):
        response = self.client.post(
            reverse("admin:queue_episodes"), {"next": "https://evil.example/"}
        )
        self.assertEqual(response["Location"], reverse("admin:processing_queue"))

    @patch(DELAY)
    def test_process_newest_action(self, mock_delay):
        self.episode("older", days_ago=2)
        newest = self.episode("newest")

        self.client.post(
            reverse("admin:podcast_action", args=[self.podcast.pk]),
            {"action": "process_newest", "count": "1"},
        )

        mock_delay.assert_called_once_with(newest.pk)

    def test_settings_action_saves(self):
        self.client.post(
            reverse("admin:podcast_action", args=[self.podcast.pk]),
            {
                "action": "settings",
                "is_active": "on",
                "auto_process": "on",
                "auto_process_count": "5",
            },
        )
        self.podcast.refresh_from_db()
        self.assertTrue(self.podcast.auto_process)
        self.assertEqual(self.podcast.auto_process_count, 5)

    def test_add_feed_rejects_duplicate(self):
        response = self.client.post(
            reverse("admin:podcast_add_feed"),
            {"step": "preview", "url": self.podcast.url},
        )
        self.assertContains(response, "already added")

    @patch("audio_processing.admin.dashboard_views.requests.get")
    def test_add_feed_preview_and_create(self, mock_get):
        mock_get.return_value = Mock(
            content=b"""<?xml version="1.0"?><rss version="2.0"><channel>
            <title>New Show</title>
            <item><title>Ep 1</title><enclosure url="https://n.example/1.mp3" type="audio/mpeg"/></item>
            </channel></rss>""",
            raise_for_status=Mock(),
        )
        url = "https://new.example/rss"

        preview = self.client.post(
            reverse("admin:podcast_add_feed"), {"step": "preview", "url": url}
        )
        self.assertContains(preview, "New Show")
        self.assertContains(preview, "Ep 1")

        with patch(
            "audio_processing.admin.dashboard_views.import_podcast.delay"
        ) as mock_import:
            response = self.client.post(
                reverse("admin:podcast_add_feed"),
                {
                    "step": "create",
                    "url": url,
                    "feed_title": "New Show",
                    "process_latest": "2",
                    "auto_process": "on",
                    "auto_process_count": "3",
                },
            )

        podcast = Podcast.objects.get(url=url)
        self.assertRedirects(
            response,
            reverse("admin:podcast_episodes", args=[podcast.pk]),
            fetch_redirect_response=False,
        )
        self.assertTrue(podcast.auto_process)
        mock_import.assert_called_once_with(podcast.id, process_latest=2)
