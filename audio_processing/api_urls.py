"""
API URL configuration for audio_processing project.

All API endpoints are versioned and nested under /api/v1/
"""

from django.urls import path
from .views import EpisodeViewSet, PodcastViewSet, TagsViewSet
from .views.entity_viewsets import EntityViewSet
from .views.search_viewsets import SearchViewSet

api_v1_patterns = [
    # Entities endpoints
    path(
        "entities/", EntityViewSet.as_view({"get": "list"}),
        name="api-v1-entities-list"
    ),
    path(
        "entities/<int:pk>/episodes/", EntityViewSet.as_view({"get": "episodes"}),
        name="api-v1-entities-episodes"
    ),
    path(
        "entities/<int:pk>/podcasts/", EntityViewSet.as_view({"get": "podcasts"}),
        name="api-v1-entities-podcasts"
    ),
    # Tags endpoints
    path(
        "tags/", TagsViewSet.as_view({"get": "list"}),
        name="api-v1-tags-list"
    ),
    
    # Episodes endpoints
    path(
        "episodes/top-by-views/",
        EpisodeViewSet.as_view({"get": "top_by_views"}),
        name="api-v1-episodes-top-by-views"
    ),
    path(
        "episodes/", EpisodeViewSet.as_view({"get": "list"}),
        name="api-v1-episodes-list"
    ),
    path(
        "episodes/<int:pk>/", EpisodeViewSet.as_view({"get": "retrieve"}),
        name="api-v1-episodes-retrieve"
    ),
    path(
        "episodes/<slug:slug>/",
        EpisodeViewSet.as_view({"get": "retrieve"}),
        name="api-v1-episodes-retrieve-slug"
    ),
    
    # Podcasts endpoints
    path(
        "podcasts/top-by-views/",
        PodcastViewSet.as_view({"get": "top_by_views"}),
        name="api-v1-podcasts-top-by-views"
    ),
    path(
        "podcasts/", PodcastViewSet.as_view({"get": "list"}),
        name="api-v1-podcasts-list"
    ),
    path(
        "podcasts/<int:pk>/", PodcastViewSet.as_view({"get": "retrieve"}),
        name="api-v1-podcasts-retrieve"
    ),
    path(
        "podcasts/<slug:slug>/",
        PodcastViewSet.as_view({"get": "retrieve"}),
        name="api-v1-podcasts-retrieve-slug"
    ),
    
    # Search endpoints
    path(
        "search/", SearchViewSet.as_view({"get": "search"}),
        name="api-v1-search"
    ),
]
