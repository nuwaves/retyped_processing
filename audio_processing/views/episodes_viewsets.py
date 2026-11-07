from django.utils import timezone
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, mixins, permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from audio_processing.api_filters import MultiTagFilterBackend
from audio_processing.utils.analytics import get_top_by_views
from audio_processing.utils.related import episode_entities, related_episodes

from ..models import Episode
from ..serializers import (
    EpisodeAnalyticsSerializer,
    EpisodeListSerializer,
    EpisodeSerializer,
    RelatedEpisodeSerializer,
)


# Local OrderingFilter that accepts `order_by` and maps `random` to ORDER BY RANDOM()
class OrderByFilter(filters.OrderingFilter):
    ordering_param = "order_by"

    def get_ordering(self, request, queryset, view):
        """Return ordering fields for this request.

        If the client passes `order_by=random` we return ['?'] so Django
        will execute ORDER BY RANDOM(). Otherwise fall back to the
        standard OrderingFilter behavior (respecting view.ordering_fields).
        """
        param = request.query_params.get(self.ordering_param)
        if not param:
            return super().get_ordering(request, queryset, view)

        # allow comma-separated fields; treat any 'random' token as RANDOM
        tokens = [t.strip() for t in param.split(",") if t.strip()]
        if any(t.lower() == "random" for t in tokens):
            return ["?"]

        return super().get_ordering(request, queryset, view)


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
        DjangoFilterBackend,
        OrderByFilter,
    ]
    filterset_fields = {
        "processing_completed_at": ["isnull"],
        "quotes": ["isnull"],
        # allow filtering episodes by their podcast's publication date
        "podcast__pub_date": ["gte", "lte", "isnull"],
    }

    search_fields = [
        "podcast__name",
        "title",
    ]
    lookup_field = "slug"
    ordering_fields = [
        "updated_at",
        "created_at",
        "release_date",
    ]
    ordering = ["-release_date"]

    def get_queryset(self):
        """Support extra query params like last_24h to filter by podcast pub_date."""
        qs = super().get_queryset()
        req = getattr(self, "request", None)
        if not req:
            return qs

        last_24 = req.query_params.get("last_24h")
        if last_24 and str(last_24).lower() in ("1", "true", "yes"):
            since = timezone.now() - timezone.timedelta(hours=24)
            qs = qs.filter(podcast__pub_date__gte=since)

        # has_content=true: only episodes with a summary or transcript, for
        # curated lists that shouldn't fill up with description-only episodes.
        has_content = req.query_params.get("has_content")
        if has_content and str(has_content).lower() in ("1", "true", "yes"):
            qs = qs.filter(Episode.has_content_q())

        return qs

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

    @action(detail=True, methods=["get"], url_path="related")
    def related(self, request, slug=None):
        """
        Sidebar data for an episode page: recommended episodes, plus the
        episode's topics and the people/companies it mentions for links.
        """
        episode = self.get_object()
        try:
            limit = min(max(int(request.query_params.get("limit", 5)), 1), 12)
        except ValueError:
            limit = 5
        return Response(
            {
                "episodes": RelatedEpisodeSerializer(
                    related_episodes(episode, limit=limit), many=True
                ).data,
                "topics": [
                    {"id": topic.id, "name": topic.name, "slug": topic.slug}
                    for topic in episode.topics.filter(is_enabled=True)
                ],
                "entities": [
                    {"id": entity.id, "name": entity.name, "type": entity.type}
                    for entity in episode_entities(episode)
                ],
            }
        )

    def get_serializer_class(self):
        request = getattr(self, "request", None)
        if self.action == "list":
            if (
                request
                and request.query_params.get("details", "false").lower() == "true"
            ):
                return EpisodeSerializer
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
