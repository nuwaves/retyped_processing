from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from rest_framework import serializers

from ..models import Bookmark, Episode
from .fields import HtmlSanitizedField
from .podcasts import PodcastListSerializer
from .quotes import QuoteSerializer
from .tags import TagSerializer
from .topics import TopicSerializer

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
        fields = [
            "id",
            "slug",
            "title",
            "subtitle",
            "description",
            "content_encoded",
            "summary",
            "image_url",
            "podcast",
            "tags",
            "topics",
            "quotes",
            "entities",
            "release_date",
            "pub_date",
            "duration",
            "episode_number",
            "season_number",
            "episode_type",
            "raw_audio_url",
            "audio_type",
            "audio_length",
            "itunes_explicit",
            "itunes_episode_type",
            "has_public_transcript",
            "transcript",
            "script_transcript",
            "processing_completed_at",
            "bookmark_count",
            "created_at",
            "updated_at",
        ]


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
