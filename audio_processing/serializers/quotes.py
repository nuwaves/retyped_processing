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
