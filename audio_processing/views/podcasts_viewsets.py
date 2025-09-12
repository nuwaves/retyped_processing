from django.utils import timezone
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import status
from rest_framework import viewsets, mixins, permissions, filters

from audio_processing.analytics_utils import get_top_by_views
from audio_processing.api_filters import MultiTagFilterBackend
from ..models import Podcast
from ..serializers import PodcastSerializer, PodcastListSerializer


class PodcastViewSet(
    viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin
):
    queryset = Podcast.objects.all()
    serializer_class = PodcastSerializer
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
    ]
    filter_backends = [filters.SearchFilter, MultiTagFilterBackend]
    lookup_field = 'slug'

    def get_serializer_class(self):
        if self.action in ("list",):
            return PodcastListSerializer
        return self.serializer_class

    @action(detail=False, methods=['get'], url_path='top-by-views')
    def top_by_views(self, request):
        timeframe = request.query_params.get('timeframe', 'all')
        data = get_top_by_views('podcast', Podcast, PodcastListSerializer, request, timeframe)
        return Response(data, status=status.HTTP_200_OK)
