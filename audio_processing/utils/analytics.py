import hashlib

from django.core.cache import cache
from django.db.models import Sum
from django.utils import timezone

# Trending lists change slowly and are requested on every homepage render.
TOP_BY_VIEWS_CACHE_SECONDS = 300


def get_top_by_views(entity_field, entity_model, request, timeframe="all"):
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
    # One join and GROUP BY over the analytics rows. A single filter() comes
    # before the annotation so both share one join and the sum only covers
    # the rows inside the timeframe.
    if timeframe != "all" and timeframe.endswith("d") and timeframe[:-1].isdigit():
        since = timezone.now() - timezone.timedelta(days=int(timeframe[:-1]))
        qs = entity_model.objects.filter(user_analytics__updated_at__gte=since)
    else:
        qs = entity_model.objects.filter(user_analytics__isnull=False)
    return qs.annotate(total_views=Sum("user_analytics__views")).order_by(
        "-total_views", "-id"
    )


def cached_top_by_views(request, build_response_data):
    """
    Cache a top-by-views payload for a few minutes, keyed by the full URL
    (timeframe, limit, offset). The payload is the same for every user.
    """
    digest = hashlib.md5(request.build_absolute_uri().encode()).hexdigest()
    key = f"top_by_views:{digest}"
    data = cache.get(key)
    if data is None:
        data = build_response_data()
        cache.set(key, data, TOP_BY_VIEWS_CACHE_SECONDS)
    return data
