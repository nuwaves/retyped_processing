from rest_framework import mixins, permissions, viewsets

from ..models import PodcastClaim
from ..serializers import PodcastClaimSerializer


class PodcastClaimViewSet(
    viewsets.GenericViewSet,
    mixins.ListModelMixin,
    mixins.CreateModelMixin,
):
    queryset = PodcastClaim.objects.all()
    serializer_class = PodcastClaimSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return PodcastClaim.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

