from rest_framework import serializers
from ..models import Episode
from .tags import TagSerializer
from .podcasts import PodcastListSerializer
from .quotes import QuoteSerializer
from audio_processing.utils import sanitize_html_content
from .topics import TopicSerializer

class HtmlSanitizedField(serializers.CharField):
    def to_representation(self, value):
        if isinstance(value, str):
            return sanitize_html_content(value)
        return value


class EpisodeSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True)
    podcast = PodcastListSerializer()
    followers = serializers.SerializerMethodField()
    description = HtmlSanitizedField()
    content_encoded = HtmlSanitizedField()
    summary = HtmlSanitizedField()
    quotes = QuoteSerializer(many=True)
    topics = TopicSerializer(many=True)

    def get_followers(self, obj):
        # ToDO: add follower count when we track this field
        return 0

    class Meta:
        model = Episode
        fields = "__all__"


class EpisodeListSerializer(EpisodeSerializer):
    followers = serializers.SerializerMethodField()

    def get_followers(self, obj):
        # ToDO: add follower count when we track this field
        return 0

    class Meta:
        model = Episode
        fields = [
            "id",
            "slug",
            "tags",
            "title",
            "subtitle",
            "description",
            "summary",
            "release_date",
            "created_at",
            "updated_at",
            "podcast",
            "image_url",
            "episode_number",
            "followers",
        ]


class EpisodeAnalyticsSerializer(EpisodeListSerializer):
    total_views = serializers.IntegerField(read_only=True)

    class Meta(EpisodeListSerializer.Meta):
        fields = EpisodeListSerializer.Meta.fields + ["total_views"]
