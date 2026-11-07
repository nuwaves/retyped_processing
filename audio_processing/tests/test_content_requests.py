from datetime import UTC, datetime
from unittest.mock import patch

from constance.test import override_config
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APIClient

from audio_processing.models import ContentRequest, Episode, Podcast


@override_config(CONTENT_REQUESTS_PER_DAY=1, CONTENT_REQUESTS_PER_MONTH=5)
class EpisodeContentRequestTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="reader", password="pw")
        self.podcast = Podcast.objects.create(name="Show", url="https://example.com/s")
        self.episodes = [
            Episode.objects.create(
                title=f"Episode {i}",
                podcast=self.podcast,
                raw_audio_url=f"https://example.com/{i}.mp3",
                slug=f"episode-{i}",
            )
            for i in range(8)
        ]
        self.episode = self.episodes[0]

    def url(self, episode):
        return reverse(
            "v1:api-v1-episodes-content-request", kwargs={"slug": episode.slug}
        )

    def post(self, episode):
        with patch.object(Episode, "queue_processing") as queue:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(self.url(episode))
        return response, queue

    def test_signed_out_can_read_status_but_not_request(self):
        response = self.client.get(self.url(self.episode))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "not_requested")
        self.assertIsNone(response.data["quota"])

        response, queue = self.post(self.episode)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        queue.assert_not_called()
        self.assertFalse(ContentRequest.objects.exists())

    def test_request_queues_realtime_processing(self):
        self.client.force_authenticate(self.user)
        response, queue = self.post(self.episode)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], "processing")
        self.assertTrue(response.data["requested"])
        self.assertEqual(response.data["quota"]["used_today"], 1)
        self.assertEqual(response.data["quota"]["remaining"], 0)
        queue.assert_called_once_with(realtime=True)
        self.assertTrue(
            ContentRequest.objects.filter(user=self.user, episode=self.episode).exists()
        )

    def test_daily_limit(self):
        self.client.force_authenticate(self.user)
        self.post(self.episodes[0])

        response, queue = self.post(self.episodes[1])
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data["code"], "quota_exceeded")
        self.assertIsNotNone(response.data["quota"]["resets_at"])
        queue.assert_not_called()
        self.assertEqual(ContentRequest.objects.count(), 1)

    def test_monthly_limit(self):
        self.client.force_authenticate(self.user)
        # Five requests on five earlier days this month.
        now = datetime(2026, 11, 20, 12, tzinfo=UTC)
        for day, episode in zip(range(1, 6), self.episodes[1:6]):
            request = ContentRequest.objects.create(user=self.user, episode=episode)
            ContentRequest.objects.filter(pk=request.pk).update(
                created_at=now.replace(day=day)
            )

        with patch.object(timezone, "now", return_value=now):
            response, queue = self.post(self.episode)

        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertEqual(response.data["quota"]["used_this_month"], 5)
        self.assertTrue(response.data["quota"]["resets_at"].startswith("2026-12-01"))
        queue.assert_not_called()

    def test_last_months_requests_dont_count(self):
        self.client.force_authenticate(self.user)
        now = datetime(2026, 11, 20, 12, tzinfo=UTC)
        for episode in self.episodes[1:6]:
            request = ContentRequest.objects.create(user=self.user, episode=episode)
            ContentRequest.objects.filter(pk=request.pk).update(
                created_at=datetime(2026, 10, 15, tzinfo=UTC)
            )

        with patch.object(timezone, "now", return_value=now):
            response, queue = self.post(self.episode)

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        queue.assert_called_once()

    def test_staff_have_no_limit(self):
        self.user.is_staff = True
        self.user.save()
        self.client.force_authenticate(self.user)
        for episode in self.episodes[:3]:
            response, queue = self.post(episode)
            self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["quota"]["plan"], "pro")
        self.assertIsNone(response.data["quota"]["remaining"])

    def test_episode_with_content_uses_no_request(self):
        self.episode.summary = "Already summarized."
        self.episode.save()
        self.client.force_authenticate(self.user)

        response, queue = self.post(self.episode)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "available")
        queue.assert_not_called()
        self.assertFalse(ContentRequest.objects.exists())

    def test_episode_already_processing_uses_no_request(self):
        self.episode.processing_status = Episode.ProcessingStatus.QUEUED
        self.episode.save()
        self.client.force_authenticate(self.user)

        response, queue = self.post(self.episode)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "processing")
        queue.assert_not_called()
        self.assertFalse(ContentRequest.objects.exists())

    def test_retrying_a_failed_request_uses_nothing_extra(self):
        self.client.force_authenticate(self.user)
        self.post(self.episode)
        self.episode.processing_status = Episode.ProcessingStatus.FAILED
        self.episode.save()

        response, queue = self.post(self.episode)
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        queue.assert_called_once_with(realtime=True)
        self.assertEqual(ContentRequest.objects.count(), 1)
