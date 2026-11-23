from rest_framework import mixins, permissions, viewsets
from rest_framework.throttling import UserRateThrottle

from ..models import PodcastClaim
from ..serializers import PodcastClaimSerializer


class PodcastClaimCreateThrottle(UserRateThrottle):
    """Each claim emails a third party (the podcast's RSS owner): cap it."""

    scope = "podcast_claim_create"
    rate = "10/day"

    def get_rate(self):
        return self.rate


class PodcastClaimViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
):
    queryset = PodcastClaim.objects.all()
    serializer_class = PodcastClaimSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_throttles(self):
        if self.action == "create":
            return [PodcastClaimCreateThrottle()]
        return super().get_throttles()

    def get_queryset(self):
        return PodcastClaim.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
