from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from ..models import Podcast, Episode


class EpisodeViewSetTest(TestCase):
    """Test cases for the episode API endpoints."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()

        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass'
        )
        self.client.force_authenticate(user=self.user)

        # Create test data
        self.podcast = Podcast.objects.create(
            name='Test Podcast',
            url='https://example.com/feed.xml',
            description='A podcast for testing',
            author='Test Author'
        )

        self.episode = Episode.objects.create(
            title='Test Episode',
            podcast=self.podcast,
            description='An episode for testing',
            subtitle='Test Subtitle'
        )

    def test_list_episodes(self):
        """Test listing all episodes."""
        url = reverse('v1:api-v1-episodes-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['title'], self.episode.title)

    def test_retrieve_episode(self):
        """Test retrieving a single episode."""
        url = reverse('v1:api-v1-episodes-retrieve', kwargs={'pk': self.episode.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data['title'], self.episode.title)
        self.assertEqual(data['description'], self.episode.description)
        self.assertEqual(data['subtitle'], self.episode.subtitle)
        self.assertEqual(data['podcast']['name'], self.podcast.name)

    def test_list_episodes_unauthenticated(self):
        """Test that unauthenticated requests can list episodes."""
        self.client.force_authenticate(user=None)

        url = reverse('v1:api-v1-episodes-list')
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_episode_unauthenticated(self):
        """Test that unauthenticated requests can retrieve an episode."""
        self.client.force_authenticate(user=None)

        url = reverse('v1:api-v1-episodes-retrieve', kwargs={'pk': self.episode.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
