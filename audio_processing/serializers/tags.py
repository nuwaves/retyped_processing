from rest_framework import serializers

from ..models import Tag


class TagSerializer(serializers.ModelSerializer):
    episode_count = serializers.SerializerMethodField()
    podcast_count = serializers.SerializerMethodField()

    class Meta:
        model = Tag
        fields = "__all__"

    def get_episode_count(self, obj):
        """Return the number of episodes associated with this tag."""
        # Check if already annotated (more efficient)
        if hasattr(obj, "episode_count"):
            return obj.episode_count
        # Fallback to counting (will cause N+1 if not annotated)
        return obj.episodes.count()

    def get_podcast_count(self, obj):
        """Return the number of podcasts associated with this tag."""
        # Check if already annotated (more efficient)
        if hasattr(obj, "podcast_count"):
            return obj.podcast_count
        # Fallback to counting (will cause N+1 if not annotated)
        return obj.podcasts.count()
