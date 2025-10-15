from rest_framework import serializers
from django.contrib.contenttypes.models import ContentType
from ..models import Episode, Bookmark
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
    bookmark_count = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    description = HtmlSanitizedField()
    content_encoded = HtmlSanitizedField()
    summary = HtmlSanitizedField()
    quotes = QuoteSerializer(many=True)
    topics = TopicSerializer(many=True)

    def get_bookmark_count(self, obj):
        content_type = ContentType.objects.get_for_model(Episode)
        return Bookmark.objects.filter(
            content_type=content_type,
            object_id=obj.id
        ).count()

    def get_image_url(self, obj):
        if not obj.image_url:
            return obj.podcast.image_url
        return obj.image_url

    class Meta:
        model = Episode
        fields = "__all__"


class EpisodeListSerializer(EpisodeSerializer):

    class Meta:
        model = Episode
        fields = [
            "id",
            "description",
            "title",
            "slug",
            "subtitle",
            "duration",
            "release_date",
            "image_url",
            "episode_number",
            "bookmark_count",
            "podcast"
        ]


class EpisodeAnalyticsSerializer(EpisodeListSerializer):
    total_views = serializers.IntegerField(read_only=True)

    class Meta(EpisodeListSerializer.Meta):
        fields = EpisodeListSerializer.Meta.fields + ["total_views"]
