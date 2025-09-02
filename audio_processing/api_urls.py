"""
API URL configuration for audio_processing project.

All API endpoints are versioned and nested under /api/v1/
"""

from django.urls import path
from .views import EpisodeViewSet, PodcastViewSet, TagsViewSet
from .views.search_viewsets import SearchViewSet

# API v1 URL patterns
api_v1_patterns = [
    # Tags endpoints
    path(
        "tags/", TagsViewSet.as_view({"get": "list"}),
        name="api-v1-tags-list"
    ),
    
    # Episodes endpoints
    path(
        "episodes/", EpisodeViewSet.as_view({"get": "list"}),
        name="api-v1-episodes-list"
    ),
    path(
        "episodes/<int:pk>/", EpisodeViewSet.as_view({"get": "retrieve"}),
        name="api-v1-episodes-retrieve"
    ),
    
    # Podcasts endpoints
    path(
        "podcasts/", PodcastViewSet.as_view({"get": "list"}),
        name="api-v1-podcasts-list"
    ),
    path(
        "podcasts/<int:pk>/", PodcastViewSet.as_view({"get": "retrieve"}),
        name="api-v1-podcasts-retrieve"
    ),
    
    # Search endpoints
    path(
        "search/", SearchViewSet.as_view({"get": "search"}),
        name="api-v1-search"
    ),
]
