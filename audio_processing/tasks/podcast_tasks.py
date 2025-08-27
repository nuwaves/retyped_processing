import logging
from django.utils import timezone
from ..models import Podcast, Episode
from celery import shared_task

logger = logging.getLogger(__name__)


def process_podcast_rss_feed(feed_url):
    """
    Process a podcast feed by URL.
    Creates or gets the Podcast object and processes it.
    """
    logger.info(f"Processing podcast feed: {feed_url}")

    # Get or create Podcast object
    podcast, created = Podcast.objects.get_or_create(
        url=feed_url,
        defaults={'name': f'RSS Feed from {feed_url}', 'is_active': True}
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
        return {'error': f"Podcast with ID {podcast_id} does not exist"}


@shared_task
def process_all_active_podcasts():
    """
    Celery task to process all active podcasts.
    """
    active_podcasts = Podcast.objects.filter(is_active=True)
    results = []

    for podcast in active_podcasts:
        logger.info(f"Processing podcast: {podcast.name} ({podcast.url})")
        result = podcast.process_feed()
        results.append(result)
    
    summary = {
        'total_feeds_processed': len(results),
        'feeds': results
    }

    logger.info(f"Completed processing all active podcasts: {len(results)} podcasts")
    return summary


def get_podcast_summary(podcast_id):
    """
    Get summary information about a podcast and its episodes.
    """
    try:
        podcast = Podcast.objects.get(id=podcast_id)
        return podcast.get_summary()
    except Podcast.DoesNotExist:
        return {'error': f"Podcast with ID {podcast_id} does not exist"}