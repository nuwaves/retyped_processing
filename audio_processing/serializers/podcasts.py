from django.contrib.contenttypes.models import ContentType
from django.db.models import Count
from rest_framework import serializers

from ..models import Bookmark, Follow, Podcast
from .fields import HtmlSanitizedField
from .tags import TagSerializer


class PodcastSerializer(serializers.ModelSerializer):
    description = HtmlSanitizedField()
    summary = HtmlSanitizedField()
    tags = serializers.SerializerMethodField()
    episode_count = serializers.SerializerMethodField()
    followers_count = serializers.SerializerMethodField()
    bookmark_count = serializers.SerializerMethodField()

    def get_tags(self, obj):
        """Return tags ordered by podcast count."""
        tags = obj.tags.annotate(
            podcast_count=Count("podcasts", distinct=True)
        ).order_by("-podcast_count")
        return TagSerializer(tags, many=True).data

    def get_bookmark_count(self, obj):
        content_type = ContentType.objects.get_for_model(Podcast)
        return Bookmark.objects.filter(
            content_type=content_type, object_id=obj.id
        ).count()

    def get_episode_count(self, obj):
        return obj.episodes.count()

    def get_followers_count(self, obj):
        content_type = ContentType.objects.get_for_model(Podcast)
        return Follow.objects.filter(
            content_type=content_type, object_id=obj.id
        ).count()

    class Meta:
        model = Podcast
        fields = "__all__"


class PodcastListSerializer(PodcastSerializer):
    class Meta:
        model = Podcast
        fields = [
            "id",
            "slug",
            "name",
            "tags",
            "image_url",
            "episode_count",
            "followers_count",
            "bookmark_count",
        ]


class PodcastAnalyticsSerializer(PodcastListSerializer):
    total_views = serializers.IntegerField(read_only=True)

    class Meta(PodcastListSerializer.Meta):
        fields = PodcastListSerializer.Meta.fields + ["total_views"]
