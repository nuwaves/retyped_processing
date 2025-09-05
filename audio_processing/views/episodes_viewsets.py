from ..models import Episode
from ..serializers import EpisodeSerializer, EpisodeListSerializer
from rest_framework import viewsets, mixins, permissions, filters
from audio_processing.analytics_utils import get_top_by_views
from rest_framework.response import Response
from rest_framework import status

class EpisodeViewSet(
    viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin
):
    queryset = Episode.objects.all()
    serializer_class = EpisodeSerializer
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
    ]
    filter_backends = [filters.SearchFilter]
    search_fields = [
        "podcast__name",
        "title",
    ]

    def top_by_views(self, request):
        timeframe = request.query_params.get('timeframe', 'all')
        data = get_top_by_views('episode', Episode, EpisodeListSerializer, request, timeframe)
        return Response(data, status=status.HTTP_200_OK)

    def get_serializer_class(self):
        if self.action in ("list",):
            return EpisodeListSerializer
        return self.serializer_class
