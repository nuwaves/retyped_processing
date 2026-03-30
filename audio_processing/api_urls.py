"""
API URL configuration for audio_processing project.

All API endpoints are versioned and nested under /api/v1/
"""

from django.urls import path

from .views import EpisodeViewSet, PodcastViewSet, TagsViewSet
from .views.bookmarks_viewsets import BookmarkViewSet
from .views.claim_verification_viewsets import ClaimVerificationView
from .views.entity_viewsets import EntityViewSet
from .views.feed_viewsets import FeedViewSet
from .views.follows_viewsets import FollowViewSet
from .views.podcast_claims_viewsets import PodcastClaimViewSet
from .views.search_viewsets import SearchViewSet
from .views.topics_viewsets import TopicViewSet
from .views.user_analytics_viewsets import UserAnalyticsViewSet

api_v1_patterns = [
    # Entities endpoints
    path(
        "entities/", EntityViewSet.as_view({"get": "list"}), name="api-v1-entities-list"
    ),
    path(
        "entities/<int:pk>/episodes/",
        EntityViewSet.as_view({"get": "episodes"}),
        name="api-v1-entities-episodes",
    ),
    path(
        "entities/<int:pk>/podcasts/",
        EntityViewSet.as_view({"get": "podcasts"}),
        name="api-v1-entities-podcasts",
    ),
    # Feed endpoints (authenticated)
    path(
        "feed/episodes/",
        FeedViewSet.as_view({"get": "episodes"}),
        name="api-v1-feed-episodes",
    ),
    path(
        "feed/quotes/",
        FeedViewSet.as_view({"get": "quotes"}),
        name="api-v1-feed-quotes",
    ),
    # Topics endpoints
    path("topics/", TopicViewSet.as_view({"get": "list"}), name="api-v1-topics-list"),
    path(
        "topics/<slug:slug>/",
        TopicViewSet.as_view({"get": "retrieve"}),
        name="api-v1-topics-retrieve",
    ),
    path(
        "topics/<slug:slug>/episodes/",
        TopicViewSet.as_view({"get": "episodes"}),
        name="api-v1-topics-episodes",
    ),
    path(
        "topics/<slug:slug>/quotes/",
        TopicViewSet.as_view({"get": "quotes"}),
        name="api-v1-topics-quotes",
    ),
    # Tags endpoints
    path("tags/", TagsViewSet.as_view({"get": "list"}), name="api-v1-tags-list"),
    path(
        "tags/<str:slug>",
        TagsViewSet.as_view({"get": "retrieve"}),
        name="api-v1-tags-retrieve",
    ),
    path(
        "tags/<str:slug>/episodes",
        TagsViewSet.as_view({"get": "episodes"}),
        name="api-v1-tags-retrieve-episodes",
    ),
    path(
        "tags/<str:slug>/podcasts",
        TagsViewSet.as_view({"get": "podcasts"}),
        name="api-v1-tags-retrieve-podcasts",
    ),
    # Episodes endpoints
    path(
        "episodes/top-by-views/",
        EpisodeViewSet.as_view({"get": "top_by_views"}),
        name="api-v1-episodes-top-by-views",
    ),
    path(
        "episodes/",
        EpisodeViewSet.as_view({"get": "list"}),
        name="api-v1-episodes-list",
    ),
    path(
        "episodes/<slug:slug>/",
        EpisodeViewSet.as_view({"get": "retrieve"}),
        name="api-v1-episodes-retrieve-slug",
    ),
    # Podcasts endpoints
    path(
        "podcasts/top-by-views/",
        PodcastViewSet.as_view({"get": "top_by_views"}),
        name="api-v1-podcasts-top-by-views",
    ),
    path(
        "podcasts/",
        PodcastViewSet.as_view({"get": "list"}),
        name="api-v1-podcasts-list",
    ),
    path(
        "podcasts/<slug:slug>/",
        PodcastViewSet.as_view({"get": "retrieve"}),
        name="api-v1-podcasts-retrieve-slug",
    ),
    path(
        "podcasts/<str:slug>/episodes",
        PodcastViewSet.as_view({"get": "all_episodes"}),
        name="api-v1-podcast-retrieve-episodes",
    ),
    # Search endpoints
    path("search/", SearchViewSet.as_view({"get": "search"}), name="api-v1-search"),
    # Bookmark
    path(
        "bookmarks/",
        BookmarkViewSet.as_view({"get": "list", "post": "create"}),
        name="api-v1-bookmarks",
    ),
    path(
        "bookmarks/<int:pk>/",
        BookmarkViewSet.as_view({"delete": "destroy"}),
        name="api-v1-bookmarks-detail",
    ),
    path(
        "bookmarks/<str:entity_type>/",
        BookmarkViewSet.as_view({"get": "by_entity_type"}),
        name="api-v1-bookmarks-by-type",
    ),
    path(
        "follows/",
        FollowViewSet.as_view({"get": "list", "post": "create"}),
        name="api-v1-follows",
    ),
    path(
        "follows/<int:pk>/",
        FollowViewSet.as_view({"delete": "destroy"}),
        name="api-v1-follows-detail",
    ),
    path(
        "follows/<str:entity_type>/",
        FollowViewSet.as_view({"get": "by_entity_type"}),
        name="api-v1-follows-by-type",
    ),
    path(
        "user_analytics/",
        UserAnalyticsViewSet.as_view({"get": "analytics_grouped"}),
        name="api-v1-user-analytics-grouped",
    ),
    path(
        "user_analytics/episodes",
        UserAnalyticsViewSet.as_view({"get": "analytics_only_episodes"}),
        name="api-v1-user-analytics-episodes",
    ),
    path(
        "user_analytics/podcasts",
        UserAnalyticsViewSet.as_view({"get": "analytics_only_podcasts"}),
        name="api-v1-user-analytics-podcasts",
    ),
    path(
        "podcast_claims/",
        PodcastClaimViewSet.as_view({"get": "list", "post": "create"}),
        name="api-v1-podcast-claims",
    ),
    # Claim verification endpoint
    path(
        "claims/verify/<uuid:verification_key>/",
        ClaimVerificationView.as_view(),
        name="api-v1-claims-verify",
    ),
]
