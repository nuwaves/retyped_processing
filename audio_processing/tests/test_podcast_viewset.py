from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from audio_processing.models import Podcast, UserAnalytics

class PodcastViewSetAPITest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(username='testuser', password='testpass')
        self.podcast1 = Podcast.objects.create(name='Podcast 1', url='https://example.com/1')
        self.podcast2 = Podcast.objects.create(name='Podcast 2', url='https://example.com/2')
        # Add analytics
        UserAnalytics.objects.create(user=None, podcast=self.podcast1, views=10)
        UserAnalytics.objects.create(user=None, podcast=self.podcast2, views=5)
        UserAnalytics.objects.create(user=self.user, podcast=self.podcast1, views=7)
        # Add recent analytics for timeframe test
        from django.utils import timezone
        UserAnalytics.objects.create(user=None, podcast=self.podcast2, views=20, updated_at=timezone.now())

    def test_top_by_views_all_time(self):
        url = reverse('v1:api-v1-podcasts-top-by-views')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data[0]['name'], 'Podcast 2')
        self.assertEqual(data[0]['total_views'], 25)
        self.assertEqual(data[1]['name'], 'Podcast 1')
        self.assertEqual(data[1]['total_views'], 17)

    def test_top_by_views_timeframe(self):
        url = reverse('v1:api-v1-podcasts-top-by-views')
        response = self.client.get(url, {'timeframe': '1d'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        # Only the recent analytics for podcast2 should be counted
        self.assertEqual(data[0]['name'], 'Podcast 2')
        self.assertEqual(data[0]['total_views'], 25)

    def test_top_by_views_empty(self):
        Podcast.objects.all().delete()
        url = reverse('v1:api-v1-podcasts-top-by-views')
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data, [])

    def test_retrieve_podcast_by_slug(self):
        podcast = self.podcast1
        url = reverse('v1:api-v1-podcasts-retrieve-slug', kwargs={'slug': podcast.slug})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertEqual(data['name'], podcast.name)
        self.assertEqual(data['slug'], podcast.slug)