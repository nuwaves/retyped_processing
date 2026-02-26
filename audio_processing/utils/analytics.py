from django.db.models import OuterRef, Subquery, Sum
from django.utils import timezone


def get_top_by_views(
    entity_field, entity_model, request, timeframe="all"
):
    """
    Shared utility to aggregate views for Podcast or Episode.
    Args:
        entity_field (str): 'podcast' or 'episode'
        entity_model (Model): Podcast or Episode model
        request: DRF request object
        timeframe (str): e.g. '7d', '30d', 'all'
    Returns:
        Queryset of the provided entity with the annotated field
    """
    from audio_processing.models import UserAnalytics

    qs = UserAnalytics.objects.filter(**{f"{entity_field}__isnull": False})
    if timeframe != "all":
        if timeframe.endswith("d") and timeframe[:-1].isdigit():
            days = int(timeframe[:-1])
            since = timezone.now() - timezone.timedelta(days=days)
            qs = qs.filter(updated_at__gte=since)
    entity_views = (
        qs.values(entity_field)
        .annotate(total_views=Sum("views"))
        .order_by("-total_views")
    )
    return (
        entity_model.objects.filter(id__in=entity_views.values(entity_field))
        .annotate(
            total_views=Subquery(
                entity_views.filter(**{entity_field: OuterRef("id")}).values("total_views")
            )
        )
        .order_by("-total_views")
    )
