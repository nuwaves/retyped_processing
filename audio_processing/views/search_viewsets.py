import meilisearch
from django.conf import settings
from django.db.models import Count
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ..models import Episode, Podcast, Tag
from ..models.entity import Entity
from ..models.topic import Topic
from ..serializers import SearchResultsSerializer

client = meilisearch.Client(settings.MEILISEARCH_URL, settings.MEILISEARCH_API_KEY)
episodes_index = client.index("episodes")
podcasts_index = client.index("podcasts")
entities_index = client.index("entities")


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

        # Perform search using MeiliSearch
        search_results = {}
        episode_ids = []
        podcast_ids = []

        if search_type in ["episode", "all"]:
            episode_results = episodes_index.search(
                query, {"sort": ["release_date:desc"]}
            )
            episode_ids = [hit["id"] for hit in episode_results.get("hits", [])]
            episodes_queryset = Episode.objects.filter(
                id__in=episode_ids
            ).prefetch_related("tags", "topics", "podcast")

            # Apply tag filters (OR logic - episodes must have at least one of the specified tags)
            if tag_filters:
                episodes_queryset = episodes_queryset.filter(tags__slug__in=tag_filters)

            # Apply topic filters (OR logic - episodes must have at least one of the specified topics)
            if topic_filters:
                episodes_queryset = episodes_queryset.filter(
                    topics__slug__in=topic_filters
                )

            search_results["episodes"] = episodes_queryset.distinct().order_by(
                "-release_date"
            )
            # Update episode_ids to reflect filtered results for aggregations
            episode_ids = list(search_results["episodes"].values_list("id", flat=True))

        if search_type in ["podcast", "all"]:
            podcast_results = podcasts_index.search(query)
            podcast_ids = [hit["id"] for hit in podcast_results.get("hits", [])]
            podcasts_queryset = Podcast.objects.filter(
                id__in=podcast_ids
            ).prefetch_related("tags")

            # Apply tag filters (podcasts don't have topics, only tags)
            if tag_filters:
                podcasts_queryset = podcasts_queryset.filter(tags__slug__in=tag_filters)

            search_results["podcasts"] = podcasts_queryset.distinct()
            # Update podcast_ids to reflect filtered results for aggregations
            podcast_ids = list(search_results["podcasts"].values_list("id", flat=True))

        if search_type in ["entity", "all"]:
            entity_results = entities_index.search(query)
            entity_ids = [hit["id"] for hit in entity_results.get("hits", [])]
            search_results["entities"] = Entity.objects.filter(id__in=entity_ids)

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
