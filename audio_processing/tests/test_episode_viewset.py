from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from django.contrib.auth.models import User
from audio_processing.models import Podcast, Episode, Tag
from audio_processing.models.user_analytics import UserAnalytics
from rest_framework import status

class EpisodeViewSetAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.podcast = Podcast.objects.create(name='Podcast 1', url='https://example.com/1')
        self.episode1 = Episode.objects.create(title='Episode 1', podcast=self.podcast, raw_audio_url='https://example.com/audio1.mp3', slug='episode-1')
        self.episode2 = Episode.objects.create(title='Episode 2', podcast=self.podcast, raw_audio_url='https://example.com/audio2.mp3', slug='episode-2')
        # Create tags
        self.tag1 = Tag.objects.create(name='Python', slug='python')
        self.tag2 = Tag.objects.create(name='Django', slug='django')
        self.tag3 = Tag.objects.create(name='Web Development', slug='web-development')
        # Associate tags with episodes
        self.episode1.tags.add(self.tag1, self.tag3)
        self.episode2.tags.add(self.tag2)
        # Add analytics
        UserAnalytics.objects.create(user=None, episode=self.episode1, views=10)
        UserAnalytics.objects.create(user=None, episode=self.episode2, views=5)
        UserAnalytics.objects.create(user=self.user, episode=self.episode1, views=7)
        from django.utils import timezone
        UserAnalytics.objects.create(user=None, episode=self.episode2, views=20, updated_at=timezone.now())

    def test_retrieve_creates_user_analytics_for_authenticated_user(self):
        self.client.force_authenticate(user=self.user)
        url = f'/api/episodes/{self.episode1.slug}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(UserAnalytics.objects.filter(user=self.user, episode=self.episode1).exists())

    def test_retrieve_does_not_create_user_analytics_for_anonymous(self):
        url = f'/api/episodes/{self.episode2.slug}/'
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Should not create a UserAnalytics for anonymous user
        self.assertFalse(UserAnalytics.objects.filter(user=None, episode=self.episode2, views=0).exists())

class EpisodeViewSetAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.podcast = Podcast.objects.create(name='Podcast 1', url='https://example.com/1')
        self.episode1 = Episode.objects.create(title='Episode 1', podcast=self.podcast, raw_audio_url='https://example.com/audio1.mp3')
        self.episode2 = Episode.objects.create(title='Episode 2', podcast=self.podcast, raw_audio_url='https://example.com/audio2.mp3')
        
        # Create tags
        self.tag1 = Tag.objects.create(name='Python', slug='python')
        self.tag2 = Tag.objects.create(name='Django', slug='django')
        self.tag3 = Tag.objects.create(name='Web Development', slug='web-development')
        
        # Associate tags with episodes
        self.episode1.tags.add(self.tag1, self.tag3)  # Python, Web Development
        self.episode2.tags.add(self.tag2)  # Django
        
        # Add analytics
        UserAnalytics.objects.create(user=None, episode=self.episode1, views=10)
        UserAnalytics.objects.create(user=None, episode=self.episode2, views=5)
        UserAnalytics.objects.create(user=self.user, episode=self.episode1, views=7)
        # Add recent analytics for timeframe test
        from django.utils import timezone
        UserAnalytics.objects.create(user=None, episode=self.episode2, views=20, updated_at=timezone.now())

    def test_top_by_views_all_time(self):
        url = reverse('v1:api-v1-episodes-top-by-views')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['results'][0]['title'], 'Episode 2')
        self.assertEqual(data['results'][0]['total_views'], 25)
        self.assertEqual(data['results'][1]['title'], 'Episode 1')
        self.assertEqual(data['results'][1]['total_views'], 17)

    def test_top_by_views_timeframe(self):
        url = reverse('v1:api-v1-episodes-top-by-views')
        response = self.client.get(url, {'timeframe': '1d'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        # Only the recent analytics for episode2 should be counted
        self.assertEqual(data['results'][0]['title'], 'Episode 2')
        self.assertEqual(data['results'][0]['total_views'], 25)

    def test_top_by_views_empty(self):
        Episode.objects.all().delete()
        url = reverse('v1:api-v1-episodes-top-by-views')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['results'], [])

    def test_retrieve_episode_by_slug(self):
        episode = self.episode1
        url = reverse('v1:api-v1-episodes-retrieve-slug', kwargs={'slug': episode.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['title'], episode.title)
        self.assertEqual(data['slug'], episode.slug)

    def test_filter_by_single_tag(self):
        """Test filtering episodes by a single tag slug."""
        url = reverse('v1:api-v1-episodes-list')
        response = self.client.get(url, {'tags': 'python'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['title'], 'Episode 1')

    def test_filter_by_multiple_tags(self):
        """Test filtering episodes by multiple tag slugs (OR logic)."""
        url = reverse('v1:api-v1-episodes-list')
        response = self.client.get(url, {'tags': 'python,django'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data['results']), 2)
        titles = [episode['title'] for episode in data['results']]
        self.assertIn('Episode 1', titles)
        self.assertIn('Episode 2', titles)

    def test_filter_by_nonexistent_tag(self):
        """Test filtering by a tag slug that doesn't exist."""
        url = reverse('v1:api-v1-episodes-list')
        response = self.client.get(url, {'tags': 'nonexistent'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data['results']), 2)  # Returns all results when no valid tags

    def test_filter_by_empty_tags(self):
        """Test filtering with empty tags parameter."""
        url = reverse('v1:api-v1-episodes-list')
        response = self.client.get(url, {'tags': ''})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data['results']), 2)  # Returns all results

    def test_filter_by_tags_with_spaces(self):
        """Test filtering with tag slugs that have extra spaces."""
        url = reverse('v1:api-v1-episodes-list')
        response = self.client.get(url, {'tags': ' python , django '})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data['results']), 2)
        titles = [episode['title'] for episode in data['results']]
        self.assertIn('Episode 1', titles)
        self.assertIn('Episode 2', titles)

    def test_filter_combined_search_and_tags(self):
        """Test combining search filter with tag filter."""
        url = reverse('v1:api-v1-episodes-list')
        response = self.client.get(url, {'search': 'Episode 1', 'tags': 'python'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['title'], 'Episode 1')

    def test_filter_by_hyphenated_tag_slug(self):
        """Test filtering by a tag slug with hyphens."""
        url = reverse('v1:api-v1-episodes-list')
        response = self.client.get(url, {'tags': 'web-development'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['results'][0]['title'], 'Episode 1')

    def test_top_by_views_pagination_metadata(self):
        url = reverse('v1:api-v1-episodes-top-by-views')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('count', data)
        self.assertIn('next', data)
        self.assertIn('previous', data)
        self.assertIn('results', data)
        self.assertEqual(data['count'], 2)
        self.assertIsNone(data['next'])
        self.assertIsNone(data['previous'])

    def test_top_by_views_pagination_with_page_size(self):
        url = reverse('v1:api-v1-episodes-top-by-views')
        response = self.client.get(url, {'limit': 1})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(len(data['results']), 1)
        self.assertEqual(data['count'], 2)
        self.assertIsNotNone(data['next'])
        self.assertIsNone(data['previous'])