
from unittest.mock import Mock
from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from ..models import Podcast, Episode

class EpisodeCreationFromEntryTest(TestCase):
    """Test creating episodes from RSS entry."""
    def setUp(self):
        self.podcast = Podcast.objects.create(
            name="Feed Test Podcast", url="https://example.com/test-feed.xml"
        )

    def test_create_episode_from_entry(self):
        # Mock RSS entry properly
        mock_entry = Mock()
        mock_entry.get = Mock(
            side_effect=lambda key, default=None: {"title": "Test Episode"}.get(
                key, default
            )
        )

        # Mock enclosures (audio files)
        mock_enclosure = Mock()
        mock_enclosure.get = Mock(
            side_effect=lambda key, default=None: {
                "type": "audio/mpeg",
                "href": "https://example.com/episode.mp3",
                "length": "12345678",
            }.get(key, default)
        )

        mock_entry.enclosures = [mock_enclosure]
        mock_entry.summary = 'Episode description'
        mock_entry.subtitle = 'Episode subtitle'
        mock_entry.itunes_subtitle = 'Episode subtitle'
        
        # Mock published date
        mock_entry.published_parsed = (2023, 8, 15, 10, 30, 0, 1, 227, 0)

        # Mock content attribute to avoid len() issues
        mock_content = Mock()
        mock_content.get = Mock(return_value="Episode content")
        mock_entry.content = [mock_content]

        # Mock links attribute
        mock_entry.links = []

        # Mock iTunes attributes that might be accessed but set to None/empty
        mock_entry.itunes_episode = None
        mock_entry.itunes_season = None
        mock_entry.itunes_episodetype = None
        mock_entry.itunes_explicit = None
        mock_entry.itunes_keywords = None
        mock_entry.itunes_duration = None
        
        # Mock tags as an empty list to avoid iteration issues
        mock_entry.tags = []
        
        episode = Episode.create_episode_from_entry(self.podcast, mock_entry)
        self.assertIsNotNone(episode)
        self.assertEqual(episode.title, "Test Episode")
        self.assertEqual(episode.podcast, self.podcast)
        self.assertEqual(episode.raw_audio_url, "https://example.com/episode.mp3")
        self.assertEqual(episode.audio_type, "audio/mpeg")
        self.assertEqual(episode.audio_length, 12345678)
        self.assertEqual(episode.description, "Episode description")
        self.assertEqual(episode.subtitle, "Episode subtitle")

    def test_create_episode_from_entry_no_audio(self):
        mock_entry = Mock()
        mock_entry.get = lambda key, default=None: (
            "Test Episode" if key == "title" else default
        )
        mock_entry.enclosures = []
        mock_entry.links = []

    episode = Episode.create_episode_from_entry(self.podcast, mock_entry)
    self.assertIsNone(episode)

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
        url = reverse('v1:api-v1-episodes-retrieve-slug', kwargs={'slug': self.episode.slug})
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

        url = reverse('v1:api-v1-episodes-retrieve-slug', kwargs={'slug': self.episode.slug})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
