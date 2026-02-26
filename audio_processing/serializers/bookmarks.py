from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from audio_processing.models import Bookmark
from audio_processing.serializers.episodes import EpisodeListSerializer
from audio_processing.serializers.podcasts import PodcastListSerializer


class BookmarkSerializer(serializers.ModelSerializer):
    entity_type = serializers.ChoiceField(choices=["episode", "podcast"], write_only=True)
    entity_id = serializers.IntegerField(write_only=True)
    entity = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Bookmark
        fields = ["id", "user", "entity_type", "entity_id", "entity", "created_at", "updated_at"]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def validate(self, attrs):
        entity_type = attrs.get("entity_type")
        entity_id = attrs.get("entity_id")
        user = self.context["request"].user

        content_type = ContentType.objects.get(model=entity_type)

        # Check if bookmark already exists
        if Bookmark.objects.filter(
            user=user, content_type=content_type, object_id=entity_id
        ).exists():
            raise serializers.ValidationError(
                "You have already bookmarked this item."
            )

        return attrs

    def create(self, validated_data):
        entity_type = validated_data.pop("entity_type")
        entity_id = validated_data.pop("entity_id")

        content_type = ContentType.objects.get(model=entity_type)

        bookmark = Bookmark.objects.create(
            content_type=content_type, object_id=entity_id, **validated_data
        )
        return bookmark

    def get_entity(self, obj):
        if obj.bookmarked_entity:
            if obj.content_type.model == "episode":
                return EpisodeListSerializer(obj.bookmarked_entity).data
            elif obj.content_type.model == "podcast":
                return PodcastListSerializer(obj.bookmarked_entity).data
        return None

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["entity_type"] = instance.content_type.model
        representation["entity_id"] = instance.object_id
        return representation
