from django.db.models import Count
from rest_framework import mixins, viewsets

from ..models.topic import Topic
from ..serializers.topics import TopicSerializer


class TopicViewSet(viewsets.GenericViewSet, mixins.ListModelMixin, mixins.RetrieveModelMixin):
    serializer_class = TopicSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return Topic.objects.annotate(episode_count=Count('episodes')).order_by('-episode_count')
