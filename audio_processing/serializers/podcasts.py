from rest_framework import serializers
from ..models import Podcast
from .tags import TagSerializer


class PodcastSerializer(serializers.ModelSerializer):
    tags = TagSerializer(many=True)

    class Meta:
        model = Podcast
        fields = "__all__"


class PodcastListSerializer(PodcastSerializer):
    class Meta:
        model = Podcast
        fields = [
            "id", "slug", "name", "url", "description",
            "tags", "created_at", "updated_at",
        ]
