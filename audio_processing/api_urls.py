"""
API URL configuration for audio_processing project.

All API endpoints are versioned and nested under /api/v1/
"""

from django.urls import path, re_path, include
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
    path(
        "episodes/top-by-views/",
        EpisodeViewSet.as_view({"get": "top_by_views"}),
        name="api-v1-episodes-top-by-views"
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
    path(
        "podcasts/top-by-views/",
        PodcastViewSet.as_view({"get": "top_by_views"}),
        name="api-v1-podcasts-top-by-views"
    ),
    
    # Search endpoints
    path(
        "search/", SearchViewSet.as_view({"get": "search"}),
        name="api-v1-search"
    ),
    # Auth Endpoints
    re_path(r'^auth/', include('drf_social_oauth2.urls', namespace='v1')),
]
