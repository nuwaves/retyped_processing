from rest_framework import serializers
from ..models import Podcast
from .tags import TagSerializer


class PodcastSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True)

    class Meta:
        model = Podcast
        fields = "__all__"


class PodcastListSerializer(PodcastSerializer):
    episode_count = serializers.SerializerMethodField()

    def get_episode_count(self, obj):
        return obj.episodes.count()

    class Meta:
        model = Podcast
        fields = [
            "id",
            "slug",
            "name",
            "tags",
            "image_url",
            "episode_count",
        ]


class PodcastAnalyticsSerializer(PodcastListSerializer):
    total_views = serializers.IntegerField(read_only=True)

    class Meta(PodcastListSerializer.Meta):
        fields = PodcastListSerializer.Meta.fields + ["total_views"]
