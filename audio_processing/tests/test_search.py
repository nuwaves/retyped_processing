from django.test import TestCase
from django.contrib.auth.models import User
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status
from meilisearch import Client
from django.conf import settings
import time

from ..models import Podcast, Episode, Tag
from ..models.topic import Topic


class SearchViewSetTest(TestCase):
    """Test cases for the search functionality."""
    
    def setUp(self):
        """Set up test data."""

        self.search_client = Client(settings.MEILISEARCH_URL, settings.MEILISEARCH_API_KEY)

        # Create episodes index with sortable attributes
        self.search_client.create_index("episodes", {"primaryKey": "id"})
        episodes_index = self.search_client.index("episodes")
        task = episodes_index.update_sortable_attributes(["release_date"])
        # Wait for the settings update to complete
        self.search_client.wait_for_task(task.task_uid)

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

        # Create test tags and topics
        self.tag_django = Tag.objects.create(
            name='Django',
            slug='django',
            description='Django framework content'
        )
        self.tag_web = Tag.objects.create(
            name='Web Development',
            slug='web-development',
            description='Web development topics'
        )

        # Create test topic
        self.topic = Topic.objects.create(
            topic_id=1,
            name='Web Frameworks',
            slug='web-frameworks',
            description='Discussion about web frameworks'
        )

        # Associate tags and topics with episode and podcast
        self.episode.tags.add(self.tag_django, self.tag_web)
        self.episode.topics.add(self.topic)
        self.podcast.tags.add(self.tag_django)

        # Wait a moment for Meilisearch to make documents searchable
        time.sleep(1)

    def test_search_all_content_types(self):
        """Test searching across all content types."""
        url = reverse('v1:api-v1-search')
        response = self.client.get(url, {'q': 'django'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()
        self.assertIn('podcasts', data)
        self.assertIn('episodes', data)
        self.assertIn('aggregations', data)

        # Should find our podcast
        self.assertTrue(len(data['podcasts']) > 0)
        self.assertEqual(data['podcasts'][0]['name'], 'Django Podcast')

        # Should find our episode
        self.assertTrue(len(data['episodes']) > 0)
        self.assertEqual(data['episodes'][0]['title'], 'Introduction to Django Models')

        # Test aggregations structure
        aggregations = data['aggregations']
        self.assertIn('tags', aggregations)
        self.assertIn('topics', aggregations)

        # Should have tags in aggregations
        self.assertIsInstance(aggregations['tags'], list)
        self.assertGreater(len(aggregations['tags']), 0)

        # Should have topics in aggregations
        self.assertIsInstance(aggregations['topics'], list)
        self.assertGreater(len(aggregations['topics']), 0)

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

    def test_search_aggregations(self):
        """Test that aggregations contain unique tags and topics from search results."""
        url = reverse('v1:api-v1-search')
        response = self.client.get(url, {'q': 'django'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Verify aggregations structure
        self.assertIn('aggregations', data)
        aggregations = data['aggregations']
        self.assertIn('tags', aggregations)
        self.assertIn('topics', aggregations)

        # Verify tags are deduplicated and contain expected data
        tags = aggregations['tags']
        self.assertIsInstance(tags, list)
        tag_names = [tag['name'] for tag in tags]
        self.assertIn('Django', tag_names)
        self.assertIn('Web Development', tag_names)

        # Verify each tag has expected fields
        for tag in tags:
            self.assertIn('id', tag)
            self.assertIn('name', tag)
            self.assertIn('slug', tag)

        # Verify topics contain expected data
        topics = aggregations['topics']
        self.assertIsInstance(topics, list)
        self.assertGreater(len(topics), 0)
        topic_names = [topic['name'] for topic in topics]
        self.assertIn('Web Frameworks', topic_names)

        # Verify each topic has expected fields
        for topic in topics:
            self.assertIn('id', topic)
            self.assertIn('name', topic)
            self.assertIn('slug', topic)

    def test_search_aggregations_episode_only(self):
        """Test aggregations when searching only episodes."""
        url = reverse('v1:api-v1-search')
        response = self.client.get(url, {'q': 'django', 'type': 'episode'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Should still have aggregations
        self.assertIn('aggregations', data)
        aggregations = data['aggregations']

        # Should have tags from episodes
        self.assertGreater(len(aggregations['tags']), 0)

        # Should have topics from episodes
        self.assertGreater(len(aggregations['topics']), 0)

    def test_search_aggregations_podcast_only(self):
        """Test aggregations when searching only podcasts."""
        url = reverse('v1:api-v1-search')
        response = self.client.get(url, {'q': 'django', 'type': 'podcast'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Should still have aggregations
        self.assertIn('aggregations', data)
        aggregations = data['aggregations']

        # Should have tags from podcasts
        self.assertGreater(len(aggregations['tags']), 0)

        # Topics should be empty (podcasts don't have topics)
        self.assertEqual(len(aggregations['topics']), 0)

    def test_search_aggregations_empty_results(self):
        """Test aggregations with no search results."""
        url = reverse('v1:api-v1-search')
        response = self.client.get(url, {'q': 'nonexistentquery12345'})

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        # Should still have aggregations structure
        self.assertIn('aggregations', data)
        aggregations = data['aggregations']

        # Should have empty arrays
        self.assertEqual(aggregations['tags'], [])
        self.assertEqual(aggregations['topics'], [])