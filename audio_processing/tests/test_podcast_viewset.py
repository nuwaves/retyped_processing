from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from audio_processing.models import Episode, Podcast, Tag, UserAnalytics


class PodcastViewSetAPITest(TestCase):
    def test_retrieve_creates_user_analytics_for_authenticated_user(self):
        self.client.force_authenticate(user=self.user)
        podcast = self.podcast1
        url = reverse("v1:api-v1-podcasts-retrieve-slug", kwargs={"slug": podcast.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(
            UserAnalytics.objects.filter(user=self.user, podcast=podcast).exists()
        )

    def test_retrieve_does_not_create_user_analytics_for_anonymous(self):
        podcast = self.podcast2
        url = reverse("v1:api-v1-podcasts-retrieve-slug", kwargs={"slug": podcast.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        # Should not create a UserAnalytics for anonymous user with user field set
        self.assertFalse(
            UserAnalytics.objects.filter(user__isnull=False, podcast=podcast).exists()
        )

    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.podcast1 = Podcast.objects.create(
            name="Podcast 1", url="https://example.com/1"
        )
        self.podcast2 = Podcast.objects.create(
            name="Podcast 2", url="https://example.com/2"
        )

        # Create tags
        self.tag1 = Tag.objects.create(name="Tech", slug="tech")
        self.tag2 = Tag.objects.create(name="Comedy", slug="comedy")
        self.tag3 = Tag.objects.create(name="News", slug="news")

        # Associate tags with podcasts
        self.podcast1.tags.add(self.tag1, self.tag3)  # Tech, News
        self.podcast2.tags.add(self.tag2)  # Comedy

        # Create episodes for podcasts
        self.episode1 = Episode.objects.create(
            title="Episode 1",
            podcast=self.podcast1,
            raw_audio_url="https://example.com/audio1.mp3",
        )
        self.episode2 = Episode.objects.create(
            title="Episode 2",
            podcast=self.podcast1,
            raw_audio_url="https://example.com/audio2.mp3",
        )
        self.episode3 = Episode.objects.create(
            title="Episode 3",
            podcast=self.podcast2,
            raw_audio_url="https://example.com/audio3.mp3",
        )

        # Add analytics
        UserAnalytics.objects.create(user=None, podcast=self.podcast1, views=10)
        UserAnalytics.objects.create(user=None, podcast=self.podcast2, views=5)
        UserAnalytics.objects.create(user=self.user, podcast=self.podcast1, views=7)
        # Add recent analytics for timeframe test
        from django.utils import timezone

        UserAnalytics.objects.create(
            user=None, podcast=self.podcast2, views=20, updated_at=timezone.now()
        )

    def test_top_by_views_all_time(self):
        url = reverse("v1:api-v1-podcasts-top-by-views")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["results"][0]["name"], "Podcast 2")
        self.assertEqual(data["results"][0]["total_views"], 25)
        self.assertEqual(data["results"][1]["name"], "Podcast 1")
        self.assertEqual(data["results"][1]["total_views"], 17)

    def test_top_by_views_timeframe(self):
        url = reverse("v1:api-v1-podcasts-top-by-views")
        response = self.client.get(url, {"timeframe": "1d"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        # Only the recent analytics for podcast2 should be counted
        self.assertEqual(data["results"][0]["name"], "Podcast 2")
        self.assertEqual(data["results"][0]["total_views"], 25)

    def test_top_by_views_empty(self):
        Podcast.objects.all().delete()
        url = reverse("v1:api-v1-podcasts-top-by-views")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["results"], [])

    def test_retrieve_podcast_by_slug(self):
        podcast = self.podcast1
        url = reverse("v1:api-v1-podcasts-retrieve-slug", kwargs={"slug": podcast.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["name"], podcast.name)
        self.assertEqual(data["slug"], podcast.slug)

    def test_filter_by_single_tag(self):
        """Test filtering podcasts by a single tag slug."""
        url = reverse("v1:api-v1-podcasts-list")
        response = self.client.get(url, {"tags": "tech"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["name"], "Podcast 1")

    def test_filter_by_multiple_tags(self):
        """Test filtering podcasts by multiple tag slugs (OR logic)."""
        url = reverse("v1:api-v1-podcasts-list")
        response = self.client.get(url, {"tags": "tech,comedy"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 2)
        names = [podcast["name"] for podcast in data["results"]]
        self.assertIn("Podcast 1", names)
        self.assertIn("Podcast 2", names)

    def test_filter_by_nonexistent_tag(self):
        """Test filtering by a tag slug that doesn't exist."""
        url = reverse("v1:api-v1-podcasts-list")
        response = self.client.get(url, {"tags": "nonexistent"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(
            len(data["results"]), 2
        )  # Returns all results when no valid tags

    def test_filter_by_empty_tags(self):
        """Test filtering with empty tags parameter."""
        url = reverse("v1:api-v1-podcasts-list")
        response = self.client.get(url, {"tags": ""})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 2)  # Returns all results

    def test_filter_by_tags_with_spaces(self):
        """Test filtering with tag slugs that have extra spaces."""
        url = reverse("v1:api-v1-podcasts-list")
        response = self.client.get(url, {"tags": " tech , comedy "})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 2)
        names = [podcast["name"] for podcast in data["results"]]
        self.assertIn("Podcast 1", names)
        self.assertIn("Podcast 2", names)

    def test_filter_combined_search_and_tags(self):
        """Test combining search filter with tag filter."""
        url = reverse("v1:api-v1-podcasts-list")
        response = self.client.get(url, {"search": "Podcast 1", "tags": "tech"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["results"][0]["name"], "Podcast 1")

    def test_top_by_views_pagination_metadata(self):
        url = reverse("v1:api-v1-podcasts-top-by-views")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("next", data)
        self.assertIn("previous", data)
        self.assertIn("results", data)
        self.assertEqual(data["count"], 2)
        self.assertIsNone(data["next"])
        self.assertIsNone(data["previous"])

    def test_top_by_views_pagination_with_page_size(self):
        url = reverse("v1:api-v1-podcasts-top-by-views")
        response = self.client.get(url, {"limit": 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["count"], 2)
        self.assertIsNotNone(data["next"])
        self.assertIsNone(data["previous"])

    def test_all_episodes_for_podcast(self):
        """Test getting all episodes for a specific podcast."""
        url = reverse(
            "v1:api-v1-podcast-retrieve-episodes", kwargs={"slug": self.podcast1.slug}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("results", data)
        self.assertEqual(len(data["results"]), 2)
        episode_titles = [episode["title"] for episode in data["results"]]
        self.assertIn("Episode 1", episode_titles)
        self.assertIn("Episode 2", episode_titles)

    def test_all_episodes_pagination_metadata(self):
        """Test pagination metadata for all episodes endpoint."""
        url = reverse(
            "v1:api-v1-podcast-retrieve-episodes", kwargs={"slug": self.podcast1.slug}
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("next", data)
        self.assertIn("previous", data)
        self.assertIn("results", data)
        self.assertEqual(data["count"], 2)
        self.assertIsNone(data["next"])
        self.assertIsNone(data["previous"])

    def test_all_episodes_with_pagination_limit(self):
        """Test pagination with limit for all episodes endpoint."""
        url = reverse(
            "v1:api-v1-podcast-retrieve-episodes", kwargs={"slug": self.podcast1.slug}
        )
        response = self.client.get(url, {"limit": 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        self.assertEqual(data["count"], 2)
        self.assertIsNotNone(data["next"])
        self.assertIsNone(data["previous"])

    def test_all_episodes_for_nonexistent_podcast(self):
        """Test getting episodes for a podcast that doesn't exist."""
        url = reverse(
            "v1:api-v1-podcast-retrieve-episodes",
            kwargs={"slug": "nonexistent-podcast"},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_all_episodes_for_podcast_with_no_episodes(self):
        """Test getting episodes for a podcast that has no episodes."""
        podcast_no_episodes = Podcast.objects.create(
            name="Empty Podcast", url="https://example.com/empty"
        )
        url = reverse(
            "v1:api-v1-podcast-retrieve-episodes",
            kwargs={"slug": podcast_no_episodes.slug},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data["results"], [])
        self.assertEqual(data["count"], 0)
