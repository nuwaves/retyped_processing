from rest_framework import serializers

from .entities import EntitySerializer
from .episodes import EpisodeSerializer
from .podcasts import PodcastListSerializer
from .tags import TagSerializer
from .topics import TopicSerializer


class SearchAggregationsSerializer(serializers.Serializer):
    """
    Serializer for aggregated tags and topics in search results.
    """

    tags = TagSerializer(many=True, read_only=True)
    topics = TopicSerializer(many=True, read_only=True)


class SearchResultsSerializer(serializers.Serializer):
    """
    Serializer for search response body containing episodes, podcasts,
    entities, and aggregated tags/topics.

    Response structure:
    {
        "episodes": [...],
        "podcasts": [...],
        "entities": [...],
        "aggregations": {
            "tags": [...],
            "topics": [...]
        }
    }
    """

    episodes = EpisodeSerializer(many=True, read_only=True, required=False)
    podcasts = PodcastListSerializer(many=True, read_only=True, required=False)
    entities = EntitySerializer(many=True, read_only=True, required=False)
    aggregations = SearchAggregationsSerializer(read_only=True)
