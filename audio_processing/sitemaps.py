from xml.etree.ElementTree import Element, SubElement, tostring

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.http import HttpResponse
from django.utils import timezone

from audio_processing.models import Episode, Podcast

EPISODE_SITEMAP_PAGE_SIZE = 500
PODCAST_SITEMAP_PAGE_SIZE = 500

# Static pages to include in sitemap
STATIC_PAGES = [
    'trending-shows',
]

def sitemap_index_view(request):
    """Return a sitemap index XML linking to all paginated sitemaps."""
    episode_pages = get_episode_sitemaps_with_lastmod()
    podcast_pages = get_podcast_sitemaps_with_lastmod()
    domain = getattr(settings, 'SITE_DOMAIN', request.get_host())
    protocol = 'https' if request.is_secure() else 'http'
    sitemapindex = Element('sitemapindex', xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    for key, sitemap_obj, lastmod in episode_pages:
        loc = f"{protocol}://{domain}/sitemap-{key}.xml"
        sitemap = SubElement(sitemapindex, 'sitemap')
        SubElement(sitemap, 'loc').text = loc
        SubElement(sitemap, 'lastmod').text = (lastmod or timezone.now()).isoformat()
    for key, sitemap_obj, lastmod in podcast_pages:
        loc = f"{protocol}://{domain}/sitemap-{key}.xml"
        sitemap = SubElement(sitemapindex, 'sitemap')
        SubElement(sitemap, 'loc').text = loc
        SubElement(sitemap, 'lastmod').text = (lastmod or timezone.now()).isoformat()
    # Add static pages sitemap
    loc = f"{protocol}://{domain}/sitemap-static.xml"
    sitemap = SubElement(sitemapindex, 'sitemap')
    SubElement(sitemap, 'loc').text = loc
    SubElement(sitemap, 'lastmod').text = timezone.now().isoformat()
    xml_bytes = tostring(sitemapindex, encoding='utf-8', method='xml')
    return HttpResponse(xml_bytes, content_type='application/xml')


def dynamic_sitemap_view(request, section):
    """Dynamically handle episode, podcast, and static sitemap requests."""
    from django.contrib.sitemaps.views import sitemap as sitemap_view
    
    if section == 'static':
        sitemaps = {'static': StaticPageSitemap()}
        return sitemap_view(request, section='static', sitemaps=sitemaps)
    elif section.startswith('episodes-'):
        sitemaps = get_episode_sitemaps()
        return sitemap_view(request, section=section, sitemaps=sitemaps)
    elif section.startswith('podcasts-'):
        sitemaps = get_podcast_sitemaps()
        return sitemap_view(request, section=section, sitemaps=sitemaps)
    else:
        return HttpResponse('Not Found', status=404)


class EpisodeSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def __init__(self, page=1):
        self.page = page

    def items(self):
        offset = (self.page - 1) * EPISODE_SITEMAP_PAGE_SIZE
        return Episode.objects.order_by('-updated_at')[offset:offset + EPISODE_SITEMAP_PAGE_SIZE]

    def lastmod(self, obj):
        return obj.updated_at

class PodcastSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def __init__(self, page=1):
        self.page = page

    def items(self):
        offset = (self.page - 1) * PODCAST_SITEMAP_PAGE_SIZE
        return Podcast.objects.order_by('-updated_at')[offset:offset + PODCAST_SITEMAP_PAGE_SIZE]

    def lastmod(self, obj):
        return obj.updated_at


class StaticPageSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.7

    def items(self):
        return STATIC_PAGES

    def location(self, item):
        return f'/{item}'

def get_episode_sitemaps_with_lastmod():
    """Return list of (key, sitemap, max_updated_at) tuples for episodes."""
    total = Episode.objects.count()
    num_pages = (total + EPISODE_SITEMAP_PAGE_SIZE - 1) // EPISODE_SITEMAP_PAGE_SIZE
    results = []
    for i in range(num_pages):
        page = i + 1
        key = f'episodes-{page}'
        sitemap_obj = EpisodeSitemap(page=page)
        offset = (page - 1) * EPISODE_SITEMAP_PAGE_SIZE
        page_qs = Episode.objects.order_by('-updated_at')[offset:offset + EPISODE_SITEMAP_PAGE_SIZE]
        latest = page_qs.first()
        max_updated_at = latest.updated_at if latest else None
        results.append((key, sitemap_obj, max_updated_at))
    return results


def get_episode_sitemaps():
    """Return dict of sitemaps for URL configuration."""
    return {key: sitemap_obj for key, sitemap_obj, _ in get_episode_sitemaps_with_lastmod()}

def get_podcast_sitemaps_with_lastmod():
    """Return list of (key, sitemap, max_updated_at) tuples for podcasts."""
    total = Podcast.objects.count()
    num_pages = (total + PODCAST_SITEMAP_PAGE_SIZE - 1) // PODCAST_SITEMAP_PAGE_SIZE
    results = []
    for i in range(num_pages):
        page = i + 1
        key = f'podcasts-{page}'
        sitemap_obj = PodcastSitemap(page=page)
        offset = (page - 1) * PODCAST_SITEMAP_PAGE_SIZE
        page_qs = Podcast.objects.order_by('-updated_at')[offset:offset + PODCAST_SITEMAP_PAGE_SIZE]
        latest = page_qs.first()
        max_updated_at = latest.updated_at if latest else None
        results.append((key, sitemap_obj, max_updated_at))
    return results


def get_podcast_sitemaps():
    """Return dict of sitemaps for URL configuration."""
    return {key: sitemap_obj for key, sitemap_obj, _ in get_podcast_sitemaps_with_lastmod()}
