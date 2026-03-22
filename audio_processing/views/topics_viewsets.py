from django.db.models import Count
from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ..models.topic import Topic
from ..serializers.episodes import EpisodeListSerializer
from ..serializers.topics import TopicSerializer


class TopicViewSet(
    viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin
):
    serializer_class = TopicSerializer
    lookup_field = "slug"

    def get_queryset(self):
        return (
            Topic.objects.filter(is_enabled=True)
            .annotate(episode_count=Count("episodes"))
            .order_by("-episode_count")
        )

    @action(detail=True, methods=["get"], url_path="episodes")
    def episodes(self, request, slug=None):
        topic = self.get_object()
        episodes = topic.episodes.select_related("podcast").order_by("-release_date")
        page = self.paginate_queryset(episodes)
        if page is not None:
            serializer = EpisodeListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EpisodeListSerializer(episodes, many=True)
        return Response(serializer.data)
