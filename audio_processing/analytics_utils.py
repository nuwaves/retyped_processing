from django.utils import timezone
from django.db.models import Sum

def get_top_by_views(entity_field, entity_model, serializer_class, request, timeframe='all'):
    """
    Shared utility to aggregate views for Podcast or Episode.
    Args:
        entity_field (str): 'podcast' or 'episode'
        entity_model (Model): Podcast or Episode model
        serializer_class (Serializer): Serializer to use for output
        request: DRF request object
        timeframe (str): e.g. '7d', '30d', 'all'
    Returns:
        List of serialized entities with total_views
    """
    from audio_processing.models import UserAnalytics
    qs = UserAnalytics.objects.filter(**{f"{entity_field}__isnull": False})
    if timeframe != 'all':
        if timeframe.endswith('d') and timeframe[:-1].isdigit():
            days = int(timeframe[:-1])
            since = timezone.now() - timezone.timedelta(days=days)
            qs = qs.filter(updated_at__gte=since)
    entity_views = (
        qs.values(entity_field)
        .annotate(total_views=Sum('views'))
        .order_by('-total_views')
    )
    entity_ids = [ev[entity_field] for ev in entity_views]
    entities = entity_model.objects.filter(id__in=entity_ids)
    views_map = {ev[entity_field]: ev['total_views'] for ev in entity_views}
    data = []
    for entity in entities:
        item = serializer_class(entity).data
        item['total_views'] = views_map.get(entity.id, 0)
        data.append(item)
    data.sort(key=lambda x: x['total_views'], reverse=True)
    return data
