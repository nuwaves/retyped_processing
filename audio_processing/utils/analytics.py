import hashlib

from django.core.cache import cache
from django.db.models import Sum
from django.utils import timezone

# Trending lists change slowly and are requested on every homepage render.
TOP_BY_VIEWS_CACHE_SECONDS = 900


# Trending (a timeframe was given) is limited to this many entries.
TRENDING_MAX_RESULTS = 100
# Episodes one show may hold in trending episodes.
TRENDING_EPISODES_PER_PODCAST = 2
# How many ranked rows to read before applying the per-show cap.
TRENDING_CANDIDATES = 400


def _timeframe_days(timeframe):
    if timeframe != "all" and timeframe.endswith("d") and timeframe[:-1].isdigit():
        return int(timeframe[:-1])
    return None


def _release_window_days(days):
    """A 7d trending list only considers episodes released in the last 30 days."""
    return max(30, days * 4)


def _trending_episodes(days):
    """
    Episodes ranked by views in the last `days` days, limited to episodes that
    have a summary or transcript and were released recently, with at most
    TRENDING_EPISODES_PER_PODCAST per show.

    Raw view counts include crawler hits, and whatever is linked from the
    homepage gets crawled most, so without the release window old episodes
    hold their place indefinitely.
    """
    from audio_processing.models import Episode

    now = timezone.now()
    rows = (
        Episode.objects.filter(
            Episode.has_content_q(),
            release_date__gte=now - timezone.timedelta(days=_release_window_days(days)),
            user_analytics__updated_at__gte=now - timezone.timedelta(days=days),
        )
        .values("id", "podcast_id")
        .annotate(total_views=Sum("user_analytics__views"))
        .order_by("-total_views", "-id")[:TRENDING_CANDIDATES]
    )
    per_podcast = {}
    views_by_id = {}
    for row in rows:
        taken = per_podcast.get(row["podcast_id"], 0)
        if taken >= TRENDING_EPISODES_PER_PODCAST:
            continue
        per_podcast[row["podcast_id"]] = taken + 1
        views_by_id[row["id"]] = row["total_views"]
        if len(views_by_id) >= TRENDING_MAX_RESULTS:
            break

    episodes = Episode.objects.filter(id__in=views_by_id).select_related("podcast")
    # The list serializer needs none of the long text fields.
    episodes = episodes.defer(
        "transcript", "script_transcript", "summary", "content_encoded"
    )
    by_id = {episode.id: episode for episode in episodes}
    ranked = []
    for episode_id, total_views in views_by_id.items():
        episode = by_id.get(episode_id)
        if episode is not None:
            episode.total_views = total_views
            ranked.append(episode)
    return ranked


def _trending_podcasts(days):
    """
    Shows ranked by views in the last `days` days on their recently released
    episodes that have a summary or transcript (the same episodes trending
    episodes considers). Show-page hits and views on back-catalogue episodes
    are not counted: both scale with how much of a show crawlers walk, not
    with readers.
    """
    from audio_processing.models import Episode, Podcast

    now = timezone.now()
    rows = (
        Episode.objects.filter(
            Episode.has_content_q(),
            release_date__gte=now - timezone.timedelta(days=_release_window_days(days)),
            user_analytics__updated_at__gte=now - timezone.timedelta(days=days),
        )
        .values("podcast_id")
        .annotate(total_views=Sum("user_analytics__views"))
        .order_by("-total_views", "-podcast_id")[:TRENDING_MAX_RESULTS]
    )
    views_by_id = {row["podcast_id"]: row["total_views"] for row in rows}
    by_id = {
        podcast.id: podcast for podcast in Podcast.objects.filter(id__in=views_by_id)
    }
    ranked = []
    for podcast_id, total_views in views_by_id.items():
        podcast = by_id.get(podcast_id)
        if podcast is not None:
            podcast.total_views = total_views
            ranked.append(podcast)
    return ranked


def get_top_by_views(entity_field, entity_model, request, timeframe="all"):
    """
    Top podcasts or episodes by views.

    With a timeframe such as '7d' this is the trending list: a ranked list of
    model instances, each with `total_views` set (see _trending_episodes and
    _trending_podcasts for how they are chosen). With 'all' it is a queryset of
    every viewed entity ordered by its all-time view count.

    Args:
        entity_field (str): 'podcast' or 'episode'
        entity_model (Model): Podcast or Episode model
        request: DRF request object
        timeframe (str): e.g. '7d', '30d', 'all'
    """
    days = _timeframe_days(timeframe)
    if days:
        if entity_field == "episode":
            return _trending_episodes(days)
        return _trending_podcasts(days)
    return (
        entity_model.objects.filter(user_analytics__isnull=False)
        .annotate(total_views=Sum("user_analytics__views"))
        .order_by("-total_views", "-id")
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
