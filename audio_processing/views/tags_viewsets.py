from ..models import Tag
from ..serializers import TagSerializer
from rest_framework import viewsets, mixins


class TagsViewSet(
    viewsets.GenericViewSet, mixins.ListModelMixin
):
    queryset = Tag.objects.all()
    serializer_class = TagSerializer
