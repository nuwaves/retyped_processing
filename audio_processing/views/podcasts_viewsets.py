from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework import viewsets, mixins, permissions, filters

from audio_processing.analytics_utils import get_top_by_views
from audio_processing.api_filters import MultiTagFilterBackend
from ..models import Podcast
from ..serializers import (
    PodcastSerializer,
    PodcastListSerializer,
    PodcastAnalyticsSerializer,
    EpisodeListSerializer,
)


class PodcastViewSet(
    viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin
):
    queryset = Podcast.objects.all()
    serializer_class = PodcastSerializer
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
    ]
    filter_backends = [filters.SearchFilter, MultiTagFilterBackend]
    lookup_field = "slug"

    def get_serializer_class(self):
        if self.action in ("list",):
            return PodcastListSerializer
        return self.serializer_class

    @action(detail=False, methods=["get"], url_path="top-by-views")
    def top_by_views(self, request):
        timeframe = request.query_params.get("timeframe", "all")
        tops_queryset = get_top_by_views("podcast", Podcast, request, timeframe)
        page = self.paginate_queryset(tops_queryset)
        if page is not None:
            serialized_data = PodcastAnalyticsSerializer(page, many=True)
            return self.get_paginated_response(serialized_data.data)
        serialized_data = PodcastAnalyticsSerializer(tops_queryset, many=True)
        return Response(serialized_data.data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"], url_path="podcast-episodes")
    def all_episodes(self, request, slug):
        episodes = self.get_object().episodes.all()
        page = self.paginate_queryset(episodes)
        if page is not None:
            serializer = EpisodeListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = EpisodeListSerializer(episodes, many=True)
        return Response(serializer.data)

    def retrieve(self, request, *args, **kwargs):
        # Create UserAnalytics instance when podcast is retrieved
        podcast = self.get_object()
        user = request.user if request.user.is_authenticated else None
        from audio_processing.models.user_analytics import UserAnalytics
        user_analytics = UserAnalytics.objects.create(user=None, podcast=podcast, views=1)
        if user:
            user_analytics.user = user
            user_analytics.save(update_fields=["user"])
        return super().retrieve(request, *args, **kwargs)
