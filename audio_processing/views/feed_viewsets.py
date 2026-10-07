from django.contrib.contenttypes.models import ContentType
from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ..models import Follow
from ..models.episode import Episode
from ..models.podcast import Podcast
from ..models.quote import Quote
from ..serializers.episodes import EpisodeListSerializer
from ..serializers.quotes import QuoteWithEpisodeSerializer


class FeedViewSet(viewsets.GenericViewSet):
    permission_classes = [permissions.IsAuthenticated]

    def _followed_podcast_ids(self, user):
        podcast_ct = ContentType.objects.get_for_model(Podcast)
        return Follow.objects.filter(user=user, content_type=podcast_ct).values_list(
            "object_id", flat=True
        )

    @action(detail=False, methods=["get"], url_path="episodes")
    def episodes(self, request):
        podcast_ids = self._followed_podcast_ids(request.user)
        queryset = (
            Episode.objects.filter(podcast_id__in=podcast_ids)
            .select_related("podcast")
            .order_by("-release_date")
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = EpisodeListSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = EpisodeListSerializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=["get"], url_path="quotes")
    def quotes(self, request):
        podcast_ids = self._followed_podcast_ids(request.user)
        queryset = (
            Quote.objects.filter(episode__podcast_id__in=podcast_ids)
            .select_related("episode", "episode__podcast")
            .order_by("-created_at")
        )
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = QuoteWithEpisodeSerializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = QuoteWithEpisodeSerializer(queryset, many=True)
        return Response(serializer.data)
