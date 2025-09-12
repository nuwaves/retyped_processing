from rest_framework import filters
from rest_framework.compat import coreapi, coreschema
from audio_processing.models import Tag


class MultiTagFilterBackend(filters.BaseFilterBackend):
    """
    Filter backend for filtering by comma-separated tag slugs.

    Usage: ?tags=slug1,slug2,slug3
    Returns objects that have ANY of the specified tags (OR logic).
    """

    def get_schema_fields(self, view):
        return [
            coreapi.Field(
                name="tags",
                required=False,
                location="query",
                schema=coreschema.String(
                    title="Tag Filter",
                    description="Comma separated list with tag slugs",
                ),
            )
        ]

    def get_schema_operation_parameters(self, view):
        return [
            {
                "name": "tags",
                "required": False,
                "in": "query",
                "description": "Comma separated list with tag slugs",
                "schema": {
                    "type": "string",
                },
            },
        ]

    def filter_queryset(self, request, queryset, view):
        tags_param = request.query_params.get("tags")

        if not tags_param:
            return queryset
        tag_slugs = [slug.strip() for slug in tags_param.split(",") if slug.strip()]

        if not tag_slugs:
            return queryset
        valid_tag_ids = Tag.objects.filter(slug__in=tag_slugs).values_list(
            "id", flat=True
        )

        if not valid_tag_ids:
            return queryset

        return queryset.filter(tags__id__in=valid_tag_ids).distinct()
