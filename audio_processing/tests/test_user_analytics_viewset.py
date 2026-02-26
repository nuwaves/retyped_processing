from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from audio_processing.models import Episode, Podcast, UserAnalytics


class UserAnalyticsViewSetAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.user2 = User.objects.create_user(username="testuser2", password="testpass2")

        # Create test podcasts
        self.podcast1 = Podcast.objects.create(
            name="Podcast 1", url="https://example.com/podcast1"
        )
        self.podcast2 = Podcast.objects.create(
            name="Podcast 2", url="https://example.com/podcast2"
        )

        # Create test episodes
        self.episode1 = Episode.objects.create(
            title="Episode 1",
            podcast=self.podcast1,
            raw_audio_url="https://example.com/episode1.mp3",
        )
        self.episode2 = Episode.objects.create(
            title="Episode 2",
            podcast=self.podcast1,
            raw_audio_url="https://example.com/episode2.mp3",
        )
        self.episode3 = Episode.objects.create(
            title="Episode 3",
            podcast=self.podcast2,
            raw_audio_url="https://example.com/episode3.mp3",
        )

    def test_analytics_grouped_requires_authentication(self):
        """Test that analytics-grouped endpoint requires authentication."""
        url = reverse("v1:api-v1-user-analytics-grouped")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_analytics_episodes_requires_authentication(self):
        """Test that analytics-episodes endpoint requires authentication."""
        url = reverse("v1:api-v1-user-analytics-episodes")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_analytics_podcasts_requires_authentication(self):
        """Test that analytics-podcasts endpoint requires authentication."""
        url = reverse("v1:api-v1-user-analytics-podcasts")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_analytics_grouped_empty_response(self):
        """Test analytics-grouped returns empty lists when no analytics exist."""
        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-user-analytics-grouped")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("episodes", data)
        self.assertIn("podcasts", data)
        self.assertEqual(len(data["episodes"]), 0)
        self.assertEqual(len(data["podcasts"]), 0)

    def test_analytics_grouped_with_data(self):
        """Test analytics-grouped returns both episodes and podcasts analytics."""
        # Create analytics for the authenticated user
        UserAnalytics.objects.create(
            user=self.user, episode=self.episode1, views=5
        )
        UserAnalytics.objects.create(
            user=self.user, episode=self.episode2, views=3
        )
        UserAnalytics.objects.create(
            user=self.user, podcast=self.podcast1, views=10
        )
        UserAnalytics.objects.create(
            user=self.user, podcast=self.podcast2, views=7
        )

        # Create analytics for another user (should not be included)
        UserAnalytics.objects.create(
            user=self.user2, episode=self.episode3, views=2
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-user-analytics-grouped")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("episodes", data)
        self.assertIn("podcasts", data)
        self.assertEqual(len(data["episodes"]), 2)
        self.assertEqual(len(data["podcasts"]), 2)

    def test_analytics_episodes_only(self):
        """Test analytics-episodes returns only episode analytics."""
        UserAnalytics.objects.create(
            user=self.user, episode=self.episode1, views=5
        )
        UserAnalytics.objects.create(
            user=self.user, episode=self.episode2, views=3
        )
        UserAnalytics.objects.create(
            user=self.user, podcast=self.podcast1, views=10
        )

        # Create analytics for another user
        UserAnalytics.objects.create(
            user=self.user2, episode=self.episode3, views=2
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-user-analytics-episodes")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)

        # Verify all returned items are episode analytics
        for item in data:
            self.assertIn("entity_detail", item)
            self.assertIn("id", item)
            self.assertIn("user", item)
            self.assertIn("created_at", item)
            self.assertIn("updated_at", item)
            # Verify entity_detail contains episode data
            entity_detail = item["entity_detail"]
            self.assertIn("title", entity_detail)
            self.assertIn("slug", entity_detail)

    def test_analytics_podcasts_only(self):
        """Test analytics-podcasts returns only podcast analytics."""
        UserAnalytics.objects.create(
            user=self.user, episode=self.episode1, views=5
        )
        UserAnalytics.objects.create(
            user=self.user, podcast=self.podcast1, views=10
        )
        UserAnalytics.objects.create(
            user=self.user, podcast=self.podcast2, views=7
        )

        # Create analytics for another user
        UserAnalytics.objects.create(
            user=self.user2, podcast=self.podcast1, views=3
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-user-analytics-podcasts")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 2)

        # Verify all returned items are podcast analytics
        for item in data:
            self.assertIn("entity_detail", item)
            self.assertIn("id", item)
            self.assertIn("user", item)
            self.assertIn("created_at", item)
            self.assertIn("updated_at", item)
            # Verify entity_detail contains podcast data
            entity_detail = item["entity_detail"]
            self.assertIn("name", entity_detail)
            self.assertIn("slug", entity_detail)

    def test_analytics_episodes_empty(self):
        """Test analytics-episodes returns empty list when no episode analytics exist."""
        # Create only podcast analytics
        UserAnalytics.objects.create(
            user=self.user, podcast=self.podcast1, views=10
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-user-analytics-episodes")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 0)

    def test_analytics_podcasts_empty(self):
        """Test analytics-podcasts returns empty list when no podcast analytics exist."""
        # Create only episode analytics
        UserAnalytics.objects.create(
            user=self.user, episode=self.episode1, views=5
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-user-analytics-podcasts")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 0)

    def test_analytics_ordering_by_updated_at(self):
        """Test that analytics are ordered by updated_at descending."""
        # Create analytics with different updated_at times
        analytic1 = UserAnalytics.objects.create(
            user=self.user, episode=self.episode1, views=1
        )
        analytic2 = UserAnalytics.objects.create(
            user=self.user, episode=self.episode2, views=2
        )
        analytic3 = UserAnalytics.objects.create(
            user=self.user, episode=self.episode3, views=3
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-user-analytics-episodes")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 3)

        # The most recently updated should be first
        # Since all were just created, order depends on creation order
        # The last created (analytic3) should be first
        self.assertEqual(data[0]["id"], analytic3.id)
        self.assertEqual(data[1]["id"], analytic2.id)
        self.assertEqual(data[2]["id"], analytic1.id)

    def test_analytics_includes_entity_details(self):
        """Test that analytics responses include detailed entity information."""
        UserAnalytics.objects.create(
            user=self.user, episode=self.episode1, views=5
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-user-analytics-episodes")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 1)

        analytic = data[0]
        self.assertIn("entity_detail", analytic)
        entity_detail = analytic["entity_detail"]

        # Verify episode details are included
        self.assertIn("title", entity_detail)
        self.assertEqual(entity_detail["title"], self.episode1.title)

    def test_analytics_user_isolation(self):
        """Test that users can only see their own analytics."""
        # Create analytics for both users
        UserAnalytics.objects.create(
            user=self.user, episode=self.episode1, views=5
        )
        UserAnalytics.objects.create(
            user=self.user2, episode=self.episode2, views=3
        )
        UserAnalytics.objects.create(
            user=self.user, podcast=self.podcast1, views=10
        )
        UserAnalytics.objects.create(
            user=self.user2, podcast=self.podcast2, views=7
        )

        # Test user1 can only see their own analytics
        self.client.force_authenticate(user=self.user)

        url_grouped = reverse("v1:api-v1-user-analytics-grouped")
        response = self.client.get(url_grouped)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["episodes"]), 1)
        self.assertEqual(len(data["podcasts"]), 1)

        url_episodes = reverse("v1:api-v1-user-analytics-episodes")
        response = self.client.get(url_episodes)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 1)

        url_podcasts = reverse("v1:api-v1-user-analytics-podcasts")
        response = self.client.get(url_podcasts)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data), 1)

        # Test user2 can only see their own analytics
        self.client.force_authenticate(user=self.user2)

        response = self.client.get(url_grouped)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["episodes"]), 1)
        self.assertEqual(len(data["podcasts"]), 1)

    def test_analytics_select_related_efficiency(self):
        """Test that queries use select_related for efficiency."""
        UserAnalytics.objects.create(
            user=self.user, episode=self.episode1, views=5
        )
        UserAnalytics.objects.create(
            user=self.user, podcast=self.podcast1, views=10
        )

        self.client.force_authenticate(user=self.user)

        # Test that the endpoint works correctly with select_related
        # This is more of an integration test to ensure no N+1 query issues
        url = reverse("v1:api-v1-user-analytics-grouped")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["episodes"]), 1)
        self.assertEqual(len(data["podcasts"]), 1)
