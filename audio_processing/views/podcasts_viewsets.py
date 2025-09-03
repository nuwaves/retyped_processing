from ..models import Podcast
from ..serializers import PodcastSerializer, PodcastListSerializer
from rest_framework import viewsets, mixins, permissions, filters


class PodcastViewSet(
    viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin
):
    queryset = Podcast.objects.all()
    serializer_class = PodcastSerializer
    permission_classes = [
        permissions.IsAuthenticatedOrReadOnly,
    ]
    filter_backends = [filters.SearchFilter]

    def get_serializer_class(self):
        if self.action in ("list",):
            return PodcastListSerializer
        return self.serializer_class
