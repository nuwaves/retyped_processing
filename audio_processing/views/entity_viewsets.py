from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from audio_processing.models.entity import Entity
from audio_processing.models.episode import Episode
from audio_processing.serializers.entities import EntitySerializer
from audio_processing.serializers.episodes import EpisodeListSerializer


class EntityViewSet(viewsets.GenericViewSet, mixins.ListModelMixin):
    queryset = Entity.objects.all()
    serializer_class = EntitySerializer

    @action(detail=True, methods=["get"], url_path="episodes")
    def episodes(self, request, pk=None):
        """
        List episodes associated with this entity.
        """
        entity = self.get_object()
        episodes = Episode.objects.filter(entities=entity)
        serializer = EpisodeListSerializer(episodes, many=True)
        return Response(serializer.data)
