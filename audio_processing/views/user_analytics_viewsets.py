from rest_framework import permissions, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from ..models import UserAnalytics
from ..serializers import AnalyticDetailSerializer, AnalyticSerializer


class UserAnalyticsViewSet(viewsets.GenericViewSet):
    queryset = UserAnalytics.objects.all()
    serializer_class = AnalyticSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return UserAnalytics.objects.filter(
            user=self.request.user
        ).select_related('episode', 'podcast')

    def _get_episodes_queryset(self):
        """Helper method to get episodes analytics."""
        return self.get_queryset().filter(
            episode__isnull=False
        ).order_by("-updated_at")

    def _get_podcasts_queryset(self):
        """Helper method to get podcasts analytics."""
        return self.get_queryset().filter(
            podcast__isnull=False
        ).order_by("-updated_at")

    @action(detail=False, methods=["get"], url_path="analytics-grouped")
    def analytics_grouped(self, request):
        output = {
            "episodes": list(self._get_episodes_queryset()),
            "podcasts": list(self._get_podcasts_queryset()),
        }
        return Response(self.serializer_class(output).data)

    @action(detail=False, methods=["get"], url_path="analytics-episodes")
    def analytics_only_episodes(self, request):
        episodes = self._get_episodes_queryset()
        return Response(AnalyticDetailSerializer(episodes, many=True).data)

    @action(detail=False, methods=["get"], url_path="analytics-podcasts")
    def analytics_only_podcasts(self, request):
        podcasts = self._get_podcasts_queryset()
        return Response(AnalyticDetailSerializer(podcasts, many=True).data)
