import pytest
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from audio_processing.models.entity import Entity
from audio_processing.models.episode import Episode
from audio_processing.models.podcast import Podcast
from audio_processing.models.tag import Tag


@pytest.mark.django_db
def test_entity_endpoints_list_episodes_and_podcasts():
    client = APIClient()
    # Create test data
    entity = Entity.objects.create(name="Test Person", type=Entity.EntityType.PERSON)
    podcast = Podcast.objects.create(name="Test Podcast", slug="test-podcast", url="http://example.com")
    episode = Episode.objects.create(title="Test Episode", podcast=podcast, raw_audio_url="http://example.com/audio.mp3")
    episode.entities.add(entity)
    episode.save()
    podcast.tags.add(Tag.objects.create(name="Test Tag"))
    podcast.save()
    # Test episodes endpoint
    url_episodes = reverse("api-v1-entities-episodes", args=[entity.id])
    response_episodes = client.get(url_episodes)
    assert response_episodes.status_code == 200
    assert response_episodes.data
    assert response_episodes.data[0]["title"] == "Test Episode"
    # Test podcasts endpoint
    url_podcasts = reverse("api-v1-entities-podcasts", args=[entity.id])
    response_podcasts = client.get(url_podcasts)
    assert response_podcasts.status_code == 200
    assert response_podcasts.data
    assert response_podcasts.data[0]["name"] == "Test Podcast"
