from rest_framework import serializers

from audio_processing.models.quote import Quote


class QuoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Quote
        fields = [
            "id",
            "episode",
            "text",
            "speaker",
            "timestamp",
            "created_at",
            "updated_at",
        ]


class QuoteWithEpisodeSerializer(serializers.ModelSerializer):
    episode_title = serializers.CharField(source="episode.title", read_only=True)
    episode_slug = serializers.CharField(source="episode.slug", read_only=True)
    podcast_name = serializers.CharField(source="episode.podcast.name", read_only=True)
    podcast_slug = serializers.CharField(source="episode.podcast.slug", read_only=True)
    podcast_image_url = serializers.URLField(
        source="episode.podcast.image_url", read_only=True
    )

    class Meta:
        model = Quote
        fields = [
            "id",
            "text",
            "speaker",
            "timestamp",
            "episode_title",
            "episode_slug",
            "podcast_name",
            "podcast_slug",
            "podcast_image_url",
            "created_at",
        ]
