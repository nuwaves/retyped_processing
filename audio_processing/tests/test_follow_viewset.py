from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from audio_processing.models import Follow, Podcast, Tag


class FollowViewSetAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username="testuser", password="testpass")
        self.user2 = User.objects.create_user(username="testuser2", password="testpass2")

        # Create test data
        self.tag1 = Tag.objects.create(name="Python", slug="python")
        self.tag2 = Tag.objects.create(name="Django", slug="django")
        self.podcast1 = Podcast.objects.create(
            name="Podcast 1", url="https://example.com/1"
        )
        self.podcast2 = Podcast.objects.create(
            name="Podcast 2", url="https://example.com/2"
        )

    def test_list_follows_requires_authentication(self):
        """Test that listing follows requires authentication."""
        url = reverse("v1:api-v1-follows")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_follow_requires_authentication(self):
        """Test that creating follows requires authentication."""
        url = reverse("v1:api-v1-follows")
        data = {"entity_type": "tag", "entity_id": self.tag1.id}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_tag_follow(self):
        """Test creating a follow for a tag."""
        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-follows")
        data = {"entity_type": "tag", "entity_id": self.tag1.id}
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Follow.objects.count(), 1)
        follow = Follow.objects.first()
        self.assertEqual(follow.user, self.user)
        self.assertEqual(follow.object_id, self.tag1.id)
        self.assertEqual(follow.content_type.model, "tag")

    def test_create_podcast_follow(self):
        """Test creating a follow for a podcast."""
        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-follows")
        data = {"entity_type": "podcast", "entity_id": self.podcast1.id}
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Follow.objects.count(), 1)
        follow = Follow.objects.first()
        self.assertEqual(follow.user, self.user)
        self.assertEqual(follow.object_id, self.podcast1.id)
        self.assertEqual(follow.content_type.model, "podcast")

    def test_create_duplicate_follow_fails(self):
        """Test that creating duplicate follows fails due to unique constraint."""
        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-follows")
        data = {"entity_type": "tag", "entity_id": self.tag1.id}
        response1 = self.client.post(url, data, format="json")
        self.assertEqual(response1.status_code, status.HTTP_201_CREATED)

        # Try to create the same follow again
        response2 = self.client.post(url, data, format="json")
        self.assertEqual(response2.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(Follow.objects.count(), 1)

    def test_list_follows_returns_only_user_follows(self):
        """Test that users only see their own follows."""
        from django.contrib.contenttypes.models import ContentType

        tag_ct = ContentType.objects.get_for_model(Tag)

        # Create follows for user1
        Follow.objects.create(
            user=self.user, content_type=tag_ct, object_id=self.tag1.id
        )
        # Create follows for user2
        Follow.objects.create(
            user=self.user2, content_type=tag_ct, object_id=self.tag2.id
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-follows")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)

    def test_list_follows_includes_entity_data(self):
        """Test that follow list includes nested entity data."""
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(Tag)
        Follow.objects.create(
            user=self.user, content_type=content_type, object_id=self.tag1.id
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-follows")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 1)
        follow_data = data["results"][0]
        self.assertIn("entity", follow_data)
        self.assertIn("entity_type", follow_data)
        self.assertIn("entity_id", follow_data)
        self.assertEqual(follow_data["entity_type"], "tag")
        self.assertEqual(follow_data["entity"]["name"], self.tag1.name)

    def test_delete_follow(self):
        """Test deleting a follow."""
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(Tag)
        follow = Follow.objects.create(
            user=self.user, content_type=content_type, object_id=self.tag1.id
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-follows-detail", kwargs={"pk": follow.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(Follow.objects.count(), 0)

    def test_filter_follows_by_tag_type(self):
        """Test filtering follows by tag entity type."""
        from django.contrib.contenttypes.models import ContentType

        tag_ct = ContentType.objects.get_for_model(Tag)
        podcast_ct = ContentType.objects.get_for_model(Podcast)

        Follow.objects.create(user=self.user, content_type=tag_ct, object_id=self.tag1.id)
        Follow.objects.create(user=self.user, content_type=tag_ct, object_id=self.tag2.id)
        Follow.objects.create(
            user=self.user, content_type=podcast_ct, object_id=self.podcast1.id
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-follows-by-type", kwargs={"entity_type": "tag"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 2)
        for follow in data["results"]:
            self.assertEqual(follow["entity_type"], "tag")

    def test_filter_follows_by_podcast_type(self):
        """Test filtering follows by podcast entity type."""
        from django.contrib.contenttypes.models import ContentType

        tag_ct = ContentType.objects.get_for_model(Tag)
        podcast_ct = ContentType.objects.get_for_model(Podcast)

        Follow.objects.create(user=self.user, content_type=tag_ct, object_id=self.tag1.id)
        Follow.objects.create(
            user=self.user, content_type=podcast_ct, object_id=self.podcast1.id
        )
        Follow.objects.create(
            user=self.user, content_type=podcast_ct, object_id=self.podcast2.id
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-follows-by-type", kwargs={"entity_type": "podcast"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data["results"]), 2)
        for follow in data["results"]:
            self.assertEqual(follow["entity_type"], "podcast")

    def test_filter_follows_by_type_requires_authentication(self):
        """Test that filtering by type requires authentication."""
        url = reverse("v1:api-v1-follows-by-type", kwargs={"entity_type": "tag"})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_follow_pagination(self):
        """Test pagination for follow list."""
        from django.contrib.contenttypes.models import ContentType

        tag_ct = ContentType.objects.get_for_model(Tag)
        for i in range(15):
            tag = Tag.objects.create(name=f"Tag {i}", slug=f"tag-{i}")
            Follow.objects.create(user=self.user, content_type=tag_ct, object_id=tag.id)

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-follows")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn("count", data)
        self.assertIn("next", data)
        self.assertIn("previous", data)
        self.assertIn("results", data)
        self.assertEqual(data["count"], 15)

    def test_user_cannot_delete_other_users_follow(self):
        """Test that a user cannot delete another user's follow."""
        from django.contrib.contenttypes.models import ContentType

        content_type = ContentType.objects.get_for_model(Tag)
        follow = Follow.objects.create(
            user=self.user2, content_type=content_type, object_id=self.tag1.id
        )

        self.client.force_authenticate(user=self.user)
        url = reverse("v1:api-v1-follows-detail", kwargs={"pk": follow.id})
        response = self.client.delete(url)
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(Follow.objects.count(), 1)
