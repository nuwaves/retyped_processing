from rest_framework import serializers
from ..models import Episode
from .tags import TagSerializer
from .podcasts import PodcastListSerializer


class EpisodeSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True)
    podcast = PodcastListSerializer()

    class Meta:
        model = Episode
        fields = "__all__"


class EpisodeListSerializer(EpisodeSerializer):
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
        ]


class EpisodeAnalyticsSerializer(EpisodeListSerializer):
    total_views = serializers.IntegerField(read_only=True)

    class Meta(EpisodeListSerializer.Meta):
        fields = EpisodeListSerializer.Meta.fields + ["total_views"]
