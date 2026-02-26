from rest_framework import serializers

from audio_processing.models.entity import Entity


class EntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Entity
        fields = ["id", "name", "type", "created_at", "updated_at"]
