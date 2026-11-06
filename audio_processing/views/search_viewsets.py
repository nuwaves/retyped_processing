import re

from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db.models import BooleanField, Case, Count, F, Value, When
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ..models import Episode, Podcast, Tag
from ..models.entity import Entity
from ..models.mixins.searchable_mixin import SEARCH_CONFIG
from ..models.topic import Topic
from ..serializers import SearchResultsSerializer

DEFAULT_LIMIT = 20
MAX_LIMIT = 100


def build_search_query(text):
    """
    Turn user input into a Postgres tsquery: every word must match, and the
    last word also matches as a prefix ("djan" finds "django").

    Returns None if the input has no searchable words.
    """
    words = re.findall(r"\w+", text)
    if not words:
        return None
    terms = [f"'{word}'" for word in words]
    terms[-1] += ":*"
    return SearchQuery(" & ".join(terms), search_type="raw", config=SEARCH_CONFIG)


def parse_limit(value):
    try:
        limit = int(value)
    except (TypeError, ValueError):
        return DEFAULT_LIMIT
    return max(1, min(limit, MAX_LIMIT))


class SearchViewSet(viewsets.GenericViewSet):
    """
    Custom ViewSet for search functionality across podcasts, episodes, and tags.

    Provides a unified search endpoint that can search across multiple content types.
    """

    serializer_class = SearchResultsSerializer

    @action(detail=False, methods=["get"], url_path="search")
    def search(self, request):
        """
        Search across podcasts, episodes, tags, and entities.

        Query Parameters:
        - q: Search query (required)
        - type: Content type to search ('podcast', 'episode', 'tag', 'entity', 'all') - default: 'all'
        - tags: Comma-separated tag slugs or IDs to filter by (e.g., 'python,django')
        - topics: Comma-separated topic slugs or IDs to filter by (e.g., 'web-frameworks')
        - limit: Max results per content type (default 20, max 100)
        """
        query = request.query_params.get("q", "")
        search_type = request.query_params.get("type", "all")
        tags_param = request.query_params.get("tags", "")
        topics_param = request.query_params.get("topics", "")

        if not query:
            return Response(
                {"error": "Search query is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse filter parameters
        tag_filters = [t.strip() for t in tags_param.split(",") if t.strip()]
        topic_filters = [t.strip() for t in topics_param.split(",") if t.strip()]
        limit = parse_limit(request.query_params.get("limit"))
        search_query = build_search_query(query)

        search_results = {}
        episode_ids = []
        podcast_ids = []

        if search_type in ["episode", "all"]:
            episodes = []
            if search_query is not None:
                episodes_queryset = Episode.objects.filter(search_vector=search_query)

                # Tag filter (OR logic - at least one of the tags)
                if tag_filters:
                    episodes_queryset = episodes_queryset.filter(
                        id__in=Episode.objects.filter(tags__slug__in=tag_filters)
                    )

                # Topic filter (OR logic - at least one of the topics)
                if topic_filters:
                    episodes_queryset = episodes_queryset.filter(
                        id__in=Episode.objects.filter(topics__slug__in=topic_filters)
                    )

                # Episodes with a summary or transcript first, newest first
                # within each group, so description-only catalog episodes
                # don't push processed ones out of the results.
                episodes = list(
                    episodes_queryset.select_related("podcast")
                    .prefetch_related("tags", "topics")
                    .annotate(
                        has_content=Case(
                            When(Episode.has_content_q(), then=Value(True)),
                            default=Value(False),
                            output_field=BooleanField(),
                        )
                    )
                    .order_by(
                        "-has_content",
                        F("release_date").desc(nulls_last=True),
                        "-id",
                    )[:limit]
                )
            search_results["episodes"] = episodes
            episode_ids = [episode.id for episode in episodes]

        if search_type in ["podcast", "all"]:
            podcasts = []
            if search_query is not None:
                podcasts_queryset = Podcast.objects.filter(search_vector=search_query)

                # Tag filter (podcasts don't have topics, only tags)
                if tag_filters:
                    podcasts_queryset = podcasts_queryset.filter(
                        id__in=Podcast.objects.filter(tags__slug__in=tag_filters)
                    )

                podcasts = list(
                    podcasts_queryset.annotate(
                        rank=SearchRank(F("search_vector"), search_query)
                    )
                    .prefetch_related("tags")
                    .order_by("-rank", "-id")[:limit]
                )
            search_results["podcasts"] = podcasts
            podcast_ids = [podcast.id for podcast in podcasts]

        if search_type in ["entity", "all"]:
            entities = []
            if search_query is not None:
                entities = list(
                    Entity.objects.filter(search_vector=search_query)
                    .annotate(rank=SearchRank(F("search_vector"), search_query))
                    .order_by("-rank", "-id")[:limit]
                )
            search_results["entities"] = entities

        # Aggregate unique tags and topics from results
        aggregations = {}

        if episode_ids or podcast_ids:
            # Collect unique tags from episodes and podcasts
            all_tags = Tag.objects.none()
            if episode_ids:
                all_tags = all_tags | Tag.objects.filter(episodes__id__in=episode_ids)
            if podcast_ids:
                all_tags = all_tags | Tag.objects.filter(podcasts__id__in=podcast_ids)

            # Annotate with episode count and order by it (descending)
            all_tags = (
                all_tags.distinct()
                .annotate(episode_count=Count("episodes", distinct=True))
                .order_by("-episode_count")
            )
            aggregations["tags"] = all_tags

            # Collect unique topics from episodes
            if episode_ids:
                all_topics = Topic.objects.filter(
                    episodes__id__in=episode_ids
                ).distinct()
                aggregations["topics"] = all_topics
            else:
                aggregations["topics"] = []
        else:
            aggregations["tags"] = []
            aggregations["topics"] = []
        search_results["aggregations"] = aggregations
        serializer = self.serializer_class(search_results)
        return Response(serializer.data)
