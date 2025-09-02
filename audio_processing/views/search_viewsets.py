import meilisearch

from ..models import Podcast, Episode, Tag
from ..serializers import (
    PodcastListSerializer,
    EpisodeSerializer,
    TagSerializer
)
from django.conf import settings
from django.db.models import Q
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

client = meilisearch.Client(settings.MEILISEARCH_URL, settings.MEILISEARCH_API_KEY)
episodes_index = client.index('episodes')
podcasts_index = client.index('podcasts')


class SearchViewSet(viewsets.GenericViewSet):
    """
    Custom ViewSet for search functionality across podcasts, episodes, and tags.
    
    Provides a unified search endpoint that can search across multiple content types.
    """

    @action(detail=False, methods=['get'], url_path='search')
    def search(self, request):
        """
        Search across podcasts, episodes, and tags.
        
        Query Parameters:
        - q: Search query (required)
        - type: Content type to search ('podcast', 'episode', 'tag', 'all') - default: 'all'
        """
        query = request.query_params.get('q', '')
        search_type = request.query_params.get('type', 'all')

        if not query:
            return Response({"error": "Search query is required."}, status=status.HTTP_400_BAD_REQUEST)

        # Perform search using MeiliSearch
        search_results = {}
        if search_type in ['episode', 'all']:
            episode_results = episodes_index.search(query)
            
            # Extract episode IDs from MeiliSearch results
            episode_ids = [hit['id'] for hit in episode_results.get('hits', [])]
            
            # Fetch episodes from database and serialize them
            episodes = Episode.objects.filter(id__in=episode_ids)
            search_results['episodes'] = [EpisodeSerializer(episode).data for episode in episodes]

        if search_type in ['podcast', 'all']:
            podcast_results = podcasts_index.search(query)

            # Extract podcast IDs from MeiliSearch results
            podcast_ids = [hit['id'] for hit in podcast_results.get('hits', [])]

            # Fetch podcasts from database and serialize them
            podcasts = Podcast.objects.filter(id__in=podcast_ids)
            search_results['podcasts'] = [PodcastListSerializer(podcast).data for podcast in podcasts]

        return Response(search_results)