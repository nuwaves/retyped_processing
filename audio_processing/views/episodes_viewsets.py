from ..models import Episode
from ..serializers import EpisodeSerializer, EpisodeListSerializer
from rest_framework import viewsets, mixins, permissions, filters


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

    def get_serializer_class(self):
        if self.action in ("list",):
            return EpisodeListSerializer
        return self.serializer_class
