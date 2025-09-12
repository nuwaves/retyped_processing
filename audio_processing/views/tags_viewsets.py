from ..models import Tag, Episode, Podcast
from ..serializers import TagSerializer
from ..serializers.episodes import EpisodeListSerializer
from ..serializers.podcasts import PodcastListSerializer
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework import viewsets, mixins



class TagsViewSet(viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
    lookup_field = 'slug'

    @action(detail=True, methods=["get"], url_path="episodes")
    def episodes(self, request, slug=None):
        """
        List episodes associated with this tag.
        """
        episodes = self.get_object().episodes.all()
        page = self.paginate_queryset(episodes)
        if page is not None:
          serializer = EpisodeListSerializer(page, many=True)
          return self.get_paginated_response(serializer.data)
        
        serializer = EpisodeListSerializer(episodes, many=True)
        return Response(serializer.data)

    @action(detail=True, methods=["get"], url_path="podcasts")
    def podcasts(self, request, slug=None):
        """
        List podcasts associated with this tag.
        """
        podcasts = self.get_object().podcasts.all()
        page = self.paginate_queryset(podcasts)
        if page is not None:
          serializer = PodcastListSerializer(page, many=True)
          return self.get_paginated_response(serializer.data)
        serializer = PodcastListSerializer(podcasts, many=True)
        return Response(serializer.data)