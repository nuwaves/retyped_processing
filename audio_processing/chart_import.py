"""
Add the shows on Apple's podcast charts to Retyped.

Shows are created with auto-processing off and every feed episode is imported,
so they get show and episode pages without any transcription or LLM cost.
Publisher transcripts in the feeds are still picked up by the hourly
find_publisher_transcripts job.
"""

import logging
from urllib.parse import urlparse

import requests
from django.conf import settings

from audio_processing.models import Podcast
from audio_processing.transcript_manager import USER_AGENT

logger = logging.getLogger(__name__)

CHART_URL = (
    "https://rss.marketingtools.apple.com/api/v2/{country}/podcasts/top/{limit}/"
    "podcasts.json"
)
LOOKUP_URL = "https://itunes.apple.com/lookup"
# The iTunes lookup API takes a comma-separated list of ids; keep URLs short.
LOOKUP_BATCH_SIZE = 50
URL_MAX_LENGTH = Podcast._meta.get_field("url").max_length


def _get_json(url, params=None):
    resp = requests.get(
        url,
        params=params,
        timeout=settings.HTTP_TIMEOUT,
        headers={"User-Agent": USER_AGENT},
    )
    resp.raise_for_status()
    return resp.json()


def fetch_chart(country="us", limit=100):
    """Return the chart as a list of {"apple_id", "name"} dicts, in rank order."""
    data = _get_json(CHART_URL.format(country=country, limit=limit))
    return [
        {"apple_id": str(item["id"]), "name": item.get("name") or ""}
        for item in data.get("feed", {}).get("results", [])
        if item.get("id")
    ]


def lookup_feed_urls(apple_ids):
    """Map Apple podcast ids to their RSS feed URLs. Shows with no public feed are left out."""
    feeds = {}
    for start in range(0, len(apple_ids), LOOKUP_BATCH_SIZE):
        batch = apple_ids[start : start + LOOKUP_BATCH_SIZE]
        data = _get_json(
            LOOKUP_URL, params={"id": ",".join(batch), "entity": "podcast"}
        )
        for result in data.get("results", []):
            feed_url = result.get("feedUrl")
            if feed_url and result.get("collectionId"):
                feeds[str(result["collectionId"])] = feed_url
    return feeds


def feed_key(url):
    """Compare feed URLs ignoring scheme, "www.", case and a trailing slash."""
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{host}{path}{query}"


def import_top_chart(country="us", limit=100):
    """
    Create a Podcast for each charting show Retyped doesn't have yet and queue
    an import of all its episodes (none are processed). Shows already present,
    matched by feed URL or by name, are left alone.
    """
    from audio_processing.tasks.podcast_tasks import import_podcast

    chart = fetch_chart(country=country, limit=limit)
    feeds = lookup_feed_urls([show["apple_id"] for show in chart])

    known_feeds = set()
    known_names = set()
    for url, name in Podcast.objects.values_list("url", "name"):
        known_feeds.add(feed_key(url))
        known_names.add((name or "").casefold())

    created, existing, no_feed = [], [], []
    for show in chart:
        name = show["name"]
        feed_url = feeds.get(show["apple_id"])
        if not feed_url or len(feed_url) > URL_MAX_LENGTH:
            no_feed.append(name)
            continue
        key = feed_key(feed_url)
        if key in known_feeds or (name and name.casefold() in known_names):
            existing.append(name)
            continue

        podcast = Podcast.objects.create(
            url=feed_url,
            name=name or feed_url,
            is_active=True,
            auto_process=False,
        )
        known_feeds.add(key)
        known_names.add(name.casefold())
        import_podcast.delay(podcast.id, process_latest=0)
        created.append(name)

    summary = {
        "chart_size": len(chart),
        "created": created,
        "already_present": len(existing),
        "no_public_feed": no_feed,
    }
    logger.info(
        f"Chart import ({country}): {len(created)} added, {len(existing)} already "
        f"present, {len(no_feed)} without a public feed"
    )
    return summary
