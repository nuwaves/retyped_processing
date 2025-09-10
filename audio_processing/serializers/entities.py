from audio_processing.models.entity import Entity
from rest_framework import serializers

class EntitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Entity
        fields = ["id", "name", "type", "created_at", "updated_at"]
