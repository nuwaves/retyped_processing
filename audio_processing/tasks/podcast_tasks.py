import logging

from celery import shared_task

from ..models import Podcast

logger = logging.getLogger(__name__)


@shared_task
def process_podcast_rss_feed(feed_url):
    """
    Process a podcast feed by URL.
    Creates or gets the Podcast object and processes it.
    """
    logger.info(f"Processing podcast feed: {feed_url}")

    # Get or create Podcast object
    podcast, created = Podcast.objects.get_or_create(
        url=feed_url, defaults={"name": f"RSS Feed from {feed_url}", "is_active": True}
    )

    if created:
        logger.info(f"Created new Podcast object for {feed_url}")

    return podcast.process_feed()


@shared_task
def process_podcast_by_id(podcast_id):
    """
    Celery task to process a podcast by its database ID.
    """
    try:
        podcast = Podcast.objects.get(id=podcast_id)
        return podcast.process_feed()
    except Podcast.DoesNotExist:
        logger.error(f"Podcast with ID {podcast_id} does not exist")
        return {"error": f"Podcast with ID {podcast_id} does not exist"}


@shared_task
def process_all_active_podcasts():
    """
    Celery task to queue a feed refresh for every active podcast.
    Each feed runs as its own task so one slow feed can't hit the time limit for all.
    """
    podcast_ids = list(
        Podcast.objects.filter(is_active=True).values_list("id", flat=True)
    )
    for podcast_id in podcast_ids:
        process_podcast_by_id.delay(podcast_id)

    logger.info(f"Queued feed refresh for {len(podcast_ids)} active podcasts")
    return {"total_feeds_queued": len(podcast_ids)}


def get_podcast_summary(podcast_id):
    """
    Get summary information about a podcast and its episodes.
    """
    try:
        podcast = Podcast.objects.get(id=podcast_id)
        return podcast.get_summary()
    except Podcast.DoesNotExist:
        return {"error": f"Podcast with ID {podcast_id} does not exist"}


@shared_task
def index_podcast_for_search(podcast_id):
    """
    Celery task to index a single podcast for search (e.g., Meilisearch/Elasticsearch).
    """
    from audio_processing.models import Podcast

    try:
        podcast = Podcast.objects.get(id=podcast_id)
        podcast.index_to_search()
        return {"success": f"Podcast {podcast.name} indexed for search"}
    except Podcast.DoesNotExist:
        return {"error": f"Podcast with ID {podcast_id} does not exist"}
    except Exception as e:
        return {"error": str(e)}


@shared_task
def reindex_all_podcasts_for_search(batch_size=50):
    """
    Celery task to reindex all podcasts for search in batches.
    """
    from audio_processing.models import Podcast

    total_podcasts = Podcast.objects.count()
    logger.info(
        f"Starting reindex of {total_podcasts} podcasts in batches of {batch_size}"
    )
    for start in range(0, total_podcasts, batch_size):
        end = min(start + batch_size, total_podcasts)
        logger.info(f"Indexing podcasts {start + 1} to {end}")
        podcasts = Podcast.objects.all()[start:end]
        for podcast in podcasts:
            try:
                podcast.index_to_search()
            except Exception as e:
                logger.error(f"Error indexing podcast ID {podcast.id}: {str(e)}")
    logger.info("Completed reindexing all podcasts.")
