from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from audio_processing.models import Podcast, Episode, UserAnalytics

class EpisodeViewSetAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.podcast = Podcast.objects.create(name='Podcast 1', url='https://example.com/1')
        self.episode1 = Episode.objects.create(title='Episode 1', podcast=self.podcast)
        self.episode2 = Episode.objects.create(title='Episode 2', podcast=self.podcast)
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
        self.assertEqual(data[0]['title'], 'Episode 2')
        self.assertEqual(data[0]['total_views'], 25)
        self.assertEqual(data[1]['title'], 'Episode 1')
        self.assertEqual(data[1]['total_views'], 17)

    def test_top_by_views_timeframe(self):
        url = reverse('v1:api-v1-episodes-top-by-views')
        response = self.client.get(url, {'timeframe': '1d'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        # Only the recent analytics for episode2 should be counted
        self.assertEqual(data[0]['title'], 'Episode 2')
        self.assertEqual(data[0]['total_views'], 25)

    def test_top_by_views_empty(self):
        Episode.objects.all().delete()
        url = reverse('v1:api-v1-episodes-top-by-views')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data, [])

    def test_retrieve_episode_by_slug(self):
        episode = self.episode1
        url = reverse('v1:api-v1-episodes-retrieve-slug', kwargs={'slug': episode.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['title'], episode.title)
        self.assertEqual(data['slug'], episode.slug)