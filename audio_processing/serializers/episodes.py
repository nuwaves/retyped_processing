from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from rest_framework import serializers

from audio_processing.utils import sanitize_html_content

from ..models import Bookmark, Episode
from .podcasts import PodcastListSerializer
from .quotes import QuoteSerializer
from .tags import TagSerializer
from .topics import TopicSerializer


class HtmlSanitizedField(serializers.CharField):
    def to_representation(self, value):
        if isinstance(value, str):
            return sanitize_html_content(value)
        return value


class EpisodeSerializer(serializers.ModelSerializer):
    tags = serializers.SerializerMethodField()
    podcast = PodcastListSerializer()
    bookmark_count = serializers.SerializerMethodField()
    image_url = serializers.SerializerMethodField()
    description = HtmlSanitizedField()
    content_encoded = HtmlSanitizedField()
    summary = HtmlSanitizedField()
    quotes = QuoteSerializer(many=True)
    topics = TopicSerializer(many=True)

    def get_tags(self, obj):
        """Return tags ordered by episode count."""
        tags = obj.tags.annotate(
            episode_count=Count("episodes", distinct=True)
        ).order_by("-episode_count")
        return TagSerializer(tags, many=True).data

    def get_bookmark_count(self, obj):
        content_type = ContentType.objects.get_for_model(Episode)
        return Bookmark.objects.filter(
            content_type=content_type, object_id=obj.id
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
            "podcast",
        ]


class EpisodeAnalyticsSerializer(EpisodeListSerializer):
    total_views = serializers.IntegerField(read_only=True)

    class Meta(EpisodeListSerializer.Meta):
        fields = EpisodeListSerializer.Meta.fields + ["total_views"]
