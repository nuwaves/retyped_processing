from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from audio_processing.models import Bookmark, Episode, Podcast


class BookmarkViewSetAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.user2 = User.objects.create_user(username="testuser2", password="testpass2")

        # Create test data
        self.podcast1 = Podcast.objects.create(
            name="Podcast 1", url="https://example.com/1"
        )
        self.podcast2 = Podcast.objects.create(
            name="Podcast 2", url="https://example.com/2"
        )
        self.episode1 = Episode.objects.create(
            title="Episode 1",
            podcast=self.podcast1,
            raw_audio_url="https://example.com/audio1.mp3",
        )
        self.episode2 = Episode.objects.create(
            title="Episode 2",
            podcast=self.podcast2,
            raw_audio_url="https://example.com/audio2.mp3",
        )

    def test_list_bookmarks_requires_authentication(self):
        """Test that listing bookmarks requires authentication."""
        url = reverse("v1:api-v1-bookmarks")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_bookmark_requires_authentication(self):
        """Test that creating bookmarks requires authentication."""
        url = reverse("v1:api-v1-bookmarks")
        data = {"entity_type": "episode", "entity_id": self.episode1.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_episode_bookmark(self):
        """Test creating a bookmark for an episode."""
        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-bookmarks")
        data = {"entity_type": "episode", "entity_id": self.episode1.id}
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Bookmark.objects.count(), 1)
        bookmark = Bookmark.objects.first()
        self.assertEqual(bookmark.user, self.user)
        self.assertEqual(bookmark.object_id, self.episode1.id)
        self.assertEqual(bookmark.content_type.model, "episode")

    def test_create_podcast_bookmark(self):
        """Test creating a bookmark for a podcast."""
        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-bookmarks")
        data = {"entity_type": "podcast", "entity_id": self.podcast1.id}
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Bookmark.objects.count(), 1)
        bookmark = Bookmark.objects.first()
        self.assertEqual(bookmark.user, self.user)
        self.assertEqual(bookmark.object_id, self.podcast1.id)
        self.assertEqual(bookmark.content_type.model, "podcast")

    def test_create_duplicate_bookmark_fails(self):
        """Test that creating duplicate bookmarks fails due to unique constraint."""
        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-bookmarks")
        data = {"entity_type": "episode", "entity_id": self.episode1.id}
        response1 = self.client.post(url, data, format="json")
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

        # Try to create the same bookmark again
        response2 = self.client.post(url, data, format="json")
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Bookmark.objects.count(), 1)

    def test_list_bookmarks_returns_only_user_bookmarks(self):
        """Test that users only see their own bookmarks."""
        from django.contrib.contenttypes.models import ContentType

        episode_ct = ContentType.objects.get_for_model(Episode)
        podcast_ct = ContentType.objects.get_for_model(Podcast)

        # Create bookmarks for user1
        Bookmark.objects.create(
            user=self.user,
            content_type=episode_ct,
            object_id=self.episode1.id,
        )
        # Create bookmarks for user2
        Bookmark.objects.create(
            user=self.user2,
            content_type=podcast_ct,
            object_id=self.podcast1.id,
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-bookmarks")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)

    def test_list_bookmarks_includes_entity_data(self):
        """Test that bookmark list includes nested entity data."""
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(Episode)
        Bookmark.objects.create(
            user=self.user, content_type=content_type, object_id=self.episode1.id
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-bookmarks")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        bookmark_data = data["results"][0]
        self.assertIn("entity", bookmark_data)
        self.assertIn("entity_type", bookmark_data)
        self.assertIn("entity_id", bookmark_data)
        self.assertEqual(bookmark_data["entity_type"], "episode")
        self.assertEqual(bookmark_data["entity"]["title"], self.episode1.title)

    def test_delete_bookmark(self):
        """Test deleting a bookmark."""
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(Episode)
        bookmark = Bookmark.objects.create(
            user=self.user, content_type=content_type, object_id=self.episode1.id
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-bookmarks-detail", kwargs={"pk": bookmark.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Bookmark.objects.count(), 0)

    def test_filter_bookmarks_by_episode_type(self):
        """Test filtering bookmarks by episode entity type."""
        from django.contrib.contenttypes.models import ContentType

        episode_ct = ContentType.objects.get_for_model(Episode)
        podcast_ct = ContentType.objects.get_for_model(Podcast)

        Bookmark.objects.create(
            user=self.user, content_type=episode_ct, object_id=self.episode1.id
        )
        Bookmark.objects.create(
            user=self.user, content_type=episode_ct, object_id=self.episode2.id
        )
        Bookmark.objects.create(
            user=self.user, content_type=podcast_ct, object_id=self.podcast1.id
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-bookmarks-by-type", kwargs={"entity_type": "episode"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 2)
        for bookmark in data["results"]:
            self.assertEqual(bookmark["entity_type"], "episode")

    def test_filter_bookmarks_by_podcast_type(self):
        """Test filtering bookmarks by podcast entity type."""
        from django.contrib.contenttypes.models import ContentType

        episode_ct = ContentType.objects.get_for_model(Episode)
        podcast_ct = ContentType.objects.get_for_model(Podcast)

        Bookmark.objects.create(
            user=self.user, content_type=episode_ct, object_id=self.episode1.id
        )
        Bookmark.objects.create(
            user=self.user, content_type=podcast_ct, object_id=self.podcast1.id
        )
        Bookmark.objects.create(
            user=self.user, content_type=podcast_ct, object_id=self.podcast2.id
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-bookmarks-by-type", kwargs={"entity_type": "podcast"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 2)
        for bookmark in data["results"]:
            self.assertEqual(bookmark["entity_type"], "podcast")

    def test_filter_bookmarks_by_type_requires_authentication(self):
        """Test that filtering by type requires authentication."""
        url = reverse("v1:api-v1-bookmarks-by-type", kwargs={"entity_type": "episode"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_bookmark_pagination(self):
        """Test pagination for bookmark list."""
        from django.contrib.contenttypes.models import ContentType

        episode_ct = ContentType.objects.get_for_model(Episode)
        for i in range(3, 18):  # Start from 3 to avoid conflicts with setUp episodes
            episode = Episode.objects.create(
                title=f"Episode Pagination {i}",
                podcast=self.podcast1,
                raw_audio_url=f"https://example.com/audio-pagination-{i}.mp3",
            )
            Bookmark.objects.create(
                user=self.user, content_type=episode_ct, object_id=episode.id
            )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-bookmarks")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("next", data)
        self.assertIn("previous", data)
        self.assertIn("results", data)
        self.assertEqual(data["count"], 15)
