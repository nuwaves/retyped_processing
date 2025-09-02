from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from ..models import Podcast, Episode, Tag


class SearchViewSetTest(TestCase):
    """Test cases for the search functionality."""
    
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
            name='Django Podcast',
            url='https://example.com/django-feed.xml',
            description='A podcast about Django web development',
            author='Django Team',
            itunes_keywords='django,python,web,development'
        )
        
        self.episode = Episode.objects.create(
            title='Introduction to Django Models',
            podcast=self.podcast,
            description='Learn about Django ORM and models',
            subtitle='Django Models Tutorial'
        )
        
        self.tag = Tag.objects.create(
            name='python',
            slug='python',
            description='Python programming language content'
        )

    def test_search_all_content_types(self):
        """Test searching across all content types."""
        url = reverse('v1:api-v1-search')
        response = self.client.get(url, {'q': 'django'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        
        self.assertEqual(data['query'], 'django')
        self.assertEqual(data['type'], 'all')
        self.assertIn('podcasts', data)
        self.assertIn('episodes', data)
        self.assertIn('tags', data)
        
        # Should find our podcast
        self.assertTrue(len(data['podcasts']) > 0)
        self.assertEqual(data['podcasts'][0]['name'], 'Django Podcast')
        
        # Should find our episode
        self.assertTrue(len(data['episodes']) > 0)
        self.assertEqual(data['episodes'][0]['title'], 'Introduction to Django Models')

    def test_search_specific_content_type(self):
        """Test searching for a specific content type."""
        url = reverse('v1:api-v1-search')
        response = self.client.get(url, {'q': 'python', 'type': 'tag'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        
        self.assertEqual(data['type'], 'tag')
        self.assertIn('tags', data)
        self.assertNotIn('podcasts', data)  # Should only return tags
        
        # Should find our tag
        self.assertTrue(len(data['tags']) > 0)
        self.assertEqual(data['tags'][0]['name'], 'python')

    def test_search_missing_query(self):
        """Test search without query parameter."""
        url = reverse('v1:api-v1-search')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        data = response.json()
        self.assertIn('error', data)

    def test_unified_search(self):
        """Test unified search endpoint."""
        url = reverse('v1:api-v1-unified-search')
        response = self.client.get(url, {'q': 'django'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        
        self.assertEqual(data['query'], 'django')
        self.assertIn('results', data)
        self.assertIn('total_results', data)
        
        # Results should be sorted by score
        results = data['results']
        if len(results) > 1:
            for i in range(len(results) - 1):
                self.assertGreaterEqual(results[i]['score'], results[i + 1]['score'])

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

    def test_search_unauthenticated(self):
        """Test that unauthenticated requests are rejected."""
        self.client.force_authenticate(user=None)
        
        url = reverse('v1:api-v1-search')
        response = self.client.get(url, {'q': 'django'})
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
