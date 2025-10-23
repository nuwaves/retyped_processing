from rest_framework import serializers
from ..models import PodcastClaim
from rest_framework.validators import UniqueTogetherValidator


class PodcastClaimSerializer(serializers.ModelSerializer):

    class Meta:
        model = PodcastClaim
        fields = ["podcast", "user"]
        read_only_fields = ["user",]
        validators = [
            UniqueTogetherValidator(
                queryset=PodcastClaim.objects.all(),
                fields=["podcast", "user"],
                message="This podcast already has a claim by this user",
            )
        ]
