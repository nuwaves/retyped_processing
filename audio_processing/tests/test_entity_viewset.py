from unittest import skip

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from audio_processing.models.entity import Entity
from audio_processing.models.episode import Episode
from audio_processing.models.podcast import Podcast
from audio_processing.models.tag import Tag


class EntityViewSetTest(TestCase):
    @skip(
        "EntityViewSet isn't registered in any router and has no podcasts action, "
        "so these endpoints don't exist yet."
    )
    def test_entity_endpoints_list_episodes_and_podcasts(self):
        client = APIClient()
        entity = Entity.objects.create(
            name="Test Person", type=Entity.EntityType.PERSON
        )
        podcast = Podcast.objects.create(
            name="Test Podcast", slug="test-podcast", url="http://example.com"
        )
        episode = Episode.objects.create(
            title="Test Episode",
            podcast=podcast,
            raw_audio_url="http://example.com/audio.mp3",
        )
        episode.entities.add(entity)
        podcast.tags.add(Tag.objects.create(name="Test Tag"))

        url_episodes = reverse("api-v1-entities-episodes", args=[entity.id])
        response_episodes = client.get(url_episodes)
        self.assertEqual(response_episodes.status_code, 200)
        self.assertTrue(response_episodes.data)
        self.assertEqual(response_episodes.data[0]["title"], "Test Episode")

        url_podcasts = reverse("api-v1-entities-podcasts", args=[entity.id])
        response_podcasts = client.get(url_podcasts)
        self.assertEqual(response_podcasts.status_code, 200)
        self.assertTrue(response_podcasts.data)
        self.assertEqual(response_podcasts.data[0]["name"], "Test Podcast")
