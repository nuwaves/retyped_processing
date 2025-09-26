from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework import viewsets, mixins, permissions, filters

from ..models import Episode
from ..serializers import (
    EpisodeSerializer,
    EpisodeListSerializer,
    EpisodeAnalyticsSerializer,
)
from audio_processing.analytics_utils import get_top_by_views
from audio_processing.api_filters import MultiTagFilterBackend


class EpisodeViewSet(
    viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin
):
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
    ]
    filter_backends = [
        filters.SearchFilter,
        MultiTagFilterBackend,
        filters.OrderingFilter,
    ]
    search_fields = [
        "podcast__name",
        "title",
    ]
    lookup_field = "slug"
    ordering_fields = [
        "updated_at",
        "created_at",
    ]
    ordering = ["-updated_at"]

    @action(detail=False, methods=["get"], url_path="top-by-views")
    def top_by_views(self, request):
        timeframe = request.query_params.get("timeframe", "all")
        tops_queryset = get_top_by_views("episode", Episode, request, timeframe)
        page = self.paginate_queryset(tops_queryset)
        if page is not None:
            serialized_data = EpisodeAnalyticsSerializer(page, many=True)
            return self.get_paginated_response(serialized_data.data)
        serialized_data = EpisodeAnalyticsSerializer(tops_queryset, many=True)
        return Response(serialized_data.data, status=status.HTTP_200_OK)

    def get_serializer_class(self):
        if self.action in ("list",):
            return EpisodeListSerializer
        return self.serializer_class

    def retrieve(self, request, *args, **kwargs):
        # Create UserAnalytics instance when episode is retrieved
        episode = self.get_object()
        user = request.user if request.user.is_authenticated else None
        from audio_processing.models.user_analytics import UserAnalytics

        user_analytics = UserAnalytics.objects.create(
            user=None, episode=episode, views=1
        )
        if user:
            user_analytics.user = user
            user_analytics.save(update_fields=["user"])
        return super().retrieve(request, *args, **kwargs)
