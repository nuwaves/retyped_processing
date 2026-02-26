from rest_framework import serializers

from ..models import UserAnalytics
from .episodes import EpisodeListSerializer
from .podcasts import PodcastListSerializer


class AnalyticDetailSerializer(serializers.ModelSerializer):
    entity_detail = serializers.SerializerMethodField()

    def get_entity_detail(self, obj):
        """
        Get the related episode or podcast details.
        No additional queries if select_related is used in viewset.
        """
        if obj.episode:
            return EpisodeListSerializer(obj.episode).data
        if obj.podcast:
            return PodcastListSerializer(obj.podcast).data
        return None

    class Meta:
        model = UserAnalytics
        fields = ["id", "user", "entity_detail", "created_at", "updated_at"]


class AnalyticSerializer(serializers.Serializer):
    episodes = AnalyticDetailSerializer(many=True, read_only=True)
    podcasts = AnalyticDetailSerializer(many=True, read_only=True)
