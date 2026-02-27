from xml.etree.ElementTree import Element, SubElement, tostring

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.core.cache import cache
from django.http import HttpResponse
from django.utils import timezone

from audio_processing.models import Episode, Podcast

EPISODE_SITEMAP_PAGE_SIZE = 100
PODCAST_SITEMAP_PAGE_SIZE = 100
MAX_SITEMAP_PAGES = 500  # Limit total pages to prevent timeout

# Static pages to include in sitemap
STATIC_PAGES = [
    'trending-shows',
]

def sitemap_index_view(request):
    """Return a sitemap index XML linking to all paginated sitemaps."""
    # Cache the sitemap index for 1 hour to avoid expensive queries on every request
    cache_key = 'sitemap_index_xml'
    cached_response = cache.get(cache_key)
    if cached_response:
        return HttpResponse(cached_response, content_type='application/xml')
    
    domain = getattr(settings, 'SITE_DOMAIN', request.get_host())
    protocol = 'https' if request.is_secure() else 'http'
    sitemapindex = Element('sitemapindex', xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")

    # Get counts and max updated_at with minimal queries
    episode_count = Episode.objects.count()
    episode_num_pages = min(
        (episode_count + EPISODE_SITEMAP_PAGE_SIZE - 1) // EPISODE_SITEMAP_PAGE_SIZE,
        MAX_SITEMAP_PAGES
    )
    # Limit to first 1 result with index
    episode_max_updated = Episode.objects.only('updated_at').order_by('-updated_at').values_list('updated_at', flat=True)[:1]
    episode_max_updated = episode_max_updated[0] if episode_max_updated else None

    podcast_count = Podcast.objects.count()
    podcast_num_pages = min(
        (podcast_count + PODCAST_SITEMAP_PAGE_SIZE - 1) // PODCAST_SITEMAP_PAGE_SIZE,
        MAX_SITEMAP_PAGES
    )
    # Limit to first 1 result with index  
    podcast_max_updated = Podcast.objects.only('updated_at').order_by('-updated_at').values_list('updated_at', flat=True)[:1]
    podcast_max_updated = podcast_max_updated[0] if podcast_max_updated else None

    # Add episode sitemap pages
    for i in range(episode_num_pages):
        loc = f"{protocol}://{domain}/sitemap-episodes-{i+1}.xml"
        sitemap = SubElement(sitemapindex, 'sitemap')
        SubElement(sitemap, 'loc').text = loc
        SubElement(sitemap, 'lastmod').text = (episode_max_updated or timezone.now()).isoformat()

    # Add podcast sitemap pages
    for i in range(podcast_num_pages):
        loc = f"{protocol}://{domain}/sitemap-podcasts-{i+1}.xml"
        sitemap = SubElement(sitemapindex, 'sitemap')
        SubElement(sitemap, 'loc').text = loc
        SubElement(sitemap, 'lastmod').text = (podcast_max_updated or timezone.now()).isoformat()

    # Add static pages sitemap
    loc = f"{protocol}://{domain}/sitemap-static.xml"
    sitemap = SubElement(sitemapindex, 'sitemap')
    SubElement(sitemap, 'loc').text = loc
    SubElement(sitemap, 'lastmod').text = timezone.now().isoformat()

    xml_bytes = tostring(sitemapindex, encoding='utf-8', method='xml')
    
    # Cache for 1 hour (3600 seconds)
    cache.set(cache_key, xml_bytes, 3600)
    
    return HttpResponse(xml_bytes, content_type='application/xml')


def dynamic_sitemap_view(request, section):
    """Dynamically handle episode, podcast, and static sitemap requests."""
    from django.contrib.sitemaps.views import sitemap as sitemap_view
    
    if section == 'static':
        sitemaps = {'static': StaticPageSitemap()}
        return sitemap_view(request, section='static', sitemaps=sitemaps)
    elif section.startswith('episodes-'):
        # Extract page number from section (e.g., 'episodes-1' -> 1)
        try:
            page = int(section.split('-')[1])
            sitemaps = {section: EpisodeSitemap(page=page)}
            return sitemap_view(request, section=section, sitemaps=sitemaps)
        except (ValueError, IndexError):
            return HttpResponse('Not Found', status=404)
    elif section.startswith('podcasts-'):
        # Extract page number from section (e.g., 'podcasts-1' -> 1)
        try:
            page = int(section.split('-')[1])
            sitemaps = {section: PodcastSitemap(page=page)}
            return sitemap_view(request, section=section, sitemaps=sitemaps)
        except (ValueError, IndexError):
            return HttpResponse('Not Found', status=404)
    else:
        return HttpResponse('Not Found', status=404)


class EpisodeSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def __init__(self, page=1):
        self.page = page

    def items(self):
        offset = (self.page - 1) * EPISODE_SITEMAP_PAGE_SIZE
        # Only load essential fields to reduce memory usage
        return Episode.objects.only('id', 'slug', 'updated_at').order_by('-updated_at')[offset:offset + EPISODE_SITEMAP_PAGE_SIZE].iterator()

    def location(self, obj):
        return f'/episodes/{obj.slug}' if obj.slug else f'/episodes/{obj.id}'

    def lastmod(self, obj):
        return obj.updated_at

class PodcastSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def __init__(self, page=1):
        self.page = page

    def items(self):
        offset = (self.page - 1) * PODCAST_SITEMAP_PAGE_SIZE
        # Only load essential fields to reduce memory usage
        return Podcast.objects.only('id', 'slug', 'updated_at').order_by('-updated_at')[offset:offset + PODCAST_SITEMAP_PAGE_SIZE].iterator()

    def location(self, obj):
        return f'/podcasts/{obj.slug}' if obj.slug else f'/podcasts/{obj.id}'

    def lastmod(self, obj):
        return obj.updated_at


class StaticPageSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.7

    def items(self):
        return STATIC_PAGES

    def location(self, item):
        return f'/{item}'
