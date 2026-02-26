from django.contrib.contenttypes.models import ContentType
from rest_framework import serializers

from audio_processing.models import Follow
from audio_processing.serializers.podcasts import PodcastListSerializer
from audio_processing.serializers.tags import TagSerializer


class FollowSerializer(serializers.ModelSerializer):
    entity_type = serializers.ChoiceField(choices=["tag", "podcast"], write_only=True)
    entity_id = serializers.IntegerField(write_only=True)
    entity = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Follow
        fields = ["id", "user", "entity_type", "entity_id", "entity", "created_at", "updated_at"]
        read_only_fields = ["id", "user", "created_at", "updated_at"]

    def validate(self, attrs):
        entity_type = attrs.get("entity_type")
        entity_id = attrs.get("entity_id")
        user = self.context["request"].user

        content_type = ContentType.objects.get(model=entity_type)

        # Check if follow already exists
        if Follow.objects.filter(
            user=user, content_type=content_type, object_id=entity_id
        ).exists():
            raise serializers.ValidationError("You are already following this item.")

        return attrs

    def create(self, validated_data):
        entity_type = validated_data.pop("entity_type")
        entity_id = validated_data.pop("entity_id")

        content_type = ContentType.objects.get(model=entity_type)

        follow = Follow.objects.create(
            content_type=content_type, object_id=entity_id, **validated_data
        )
        return follow

    def get_entity(self, obj):
        if obj.followed_entity:
            if obj.content_type.model == "tag":
                return TagSerializer(obj.followed_entity).data
            elif obj.content_type.model == "podcast":
                return PodcastListSerializer(obj.followed_entity).data
        return None

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["entity_type"] = instance.content_type.model
        representation["entity_id"] = instance.object_id
        return representation
