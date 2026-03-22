from rest_framework import serializers

from audio_processing.models.topic import Topic


class TopicSerializer(serializers.ModelSerializer):
    episode_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Topic
        fields = (
            "id",
            "name",
            "slug",
            "description",
            "top_words",
            "episode_count",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "slug", "created_at", "updated_at")
