from ..models import Tag, Episode, Podcast
from ..serializers import TagSerializer
from ..serializers.episodes import EpisodeListSerializer
from ..serializers.podcasts import PodcastListSerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import viewsets, mixins



class TagsViewSet(viewsets.GenericViewSet, mixins.ListModelMixin):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer

    @action(detail=True, methods=["get"], url_path="episodes")
    def episodes(self, request, pk=None):
        """
        List episodes associated with this tag.
        """
        tag = self.get_object()
        episodes = Episode.objects.filter(tags=tag)
        serializer = EpisodeListSerializer(episodes, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="podcasts")
    def podcasts(self, request, pk=None):
        """
        List podcasts associated with this tag.
        """
        tag = self.get_object()
        podcasts = Podcast.objects.filter(tags=tag)
        serializer = PodcastListSerializer(podcasts, many=True)
        return Response(serializer.data)