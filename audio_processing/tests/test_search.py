from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from meilisearch import Client
from django.conf import settings

from ..models import Podcast, Episode, Tag


class SearchViewSetTest(TestCase):
    """Test cases for the search functionality."""
    
    def setUp(self):
        """Set up test data."""

        self.search_client = Client(settings.MEILISEARCH_URL, settings.MEILISEARCH_API_KEY)
        self.search_client.create_index("episodes", {"primaryKey": "id"})
        self.search_client.create_index("podcasts", {"primaryKey": "id"})
        self.search_client.create_index("entities", {"primaryKey": "id"})
        self.search_client.create_index("tags", {"primaryKey": "id"})

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
            name='Django Podcast',
            url='https://example.com/django-feed.xml',
            description='A podcast about Django web development',
            author='Django Team'
        )
        self.podcast.index_to_search()
        
        self.episode = Episode.objects.create(
            title='Introduction to Django Models',
            podcast=self.podcast,
            description='Learn about Django ORM and models',
            subtitle='Django Models Tutorial',
            transcript='In this episode, we explore Django models and how to use them effectively.'
        )
        self.episode.index_to_search()
        
        self.tag = Tag.objects.create(
            name='python',
            slug='python',
            description='Python programming language content'
        )
        if hasattr(self.tag, 'index_to_search'):
            self.tag.index_to_search()

    def test_search_all_content_types(self):
        """Test searching across all content types."""
        url = reverse('v1:api-v1-search')
        response = self.client.get(url, {'q': 'django'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('podcasts', data)
        self.assertIn('episodes', data)
        breakpoint()
        # Should find our podcast
        self.assertTrue(len(data['podcasts']) > 0)
        self.assertEqual(data['podcasts'][0]['name'], 'Django Podcast')
        
        # Should find our episode
        self.assertTrue(len(data['episodes']) > 0)
        self.assertEqual(data['episodes'][0]['title'], 'Introduction to Django Models')

    def test_search_missing_query(self):
        """Test search without query parameter."""
        url = reverse('v1:api-v1-search')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn('error', data)

    # Commented by the moment because endpoints doesn't exists
    #def test_unified_search(self):
    #    """Test unified search endpoint."""
    #    url = reverse('v1:api-v1-unified-search')
    #    response = self.client.get(url, {'q': 'django'})
    #    
    #    self.assertEqual(response.status_code, status.HTTP_200_OK)
    #    data = response.json()
    #    
    #    self.assertEqual(data['query'], 'django')
    #    self.assertIn('results', data)
    #    self.assertIn('total_results', data)
    #    
    #    # Results should be sorted by score
    #    results = data['results']
    #    if len(results) > 1:
    #        for i in range(len(results) - 1):
    #            self.assertGreaterEqual(results[i]['score'], results[i + 1]['score'])

    def test_search_limit(self):
        """Test search result limiting."""
        url = reverse('v1:api-v1-search')
        response = self.client.get(url, {'q': 'django', 'limit': '1'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        
        # Each content type should have at most 1 result
        for content_type in ['podcasts', 'episodes', 'tags']:
            if content_type in data:
                self.assertLessEqual(len(data[content_type]), 1)