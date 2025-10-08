from django.http import HttpResponse
from django.urls import reverse
from django.utils import timezone
from xml.etree.ElementTree import Element, SubElement, tostring
from django.conf import settings
from django.contrib.sitemaps import Sitemap
from audio_processing.models import Episode, Podcast

EPISODE_SITEMAP_PAGE_SIZE = 500
PODCAST_SITEMAP_PAGE_SIZE = 500

def sitemap_index_view(request):
    """Return a sitemap index XML linking to all paginated sitemaps."""
    episode_sitemaps = get_episode_sitemaps()
    podcast_sitemaps = get_podcast_sitemaps()
    domain = getattr(settings, 'SITE_DOMAIN', request.get_host())
    protocol = 'https' if request.is_secure() else 'http'
    sitemapindex = Element('sitemapindex', xmlns="http://www.sitemaps.org/schemas/sitemap/0.9")
    now = timezone.now().isoformat()
    for key in episode_sitemaps:
        loc = f"{protocol}://{domain}/sitemap-{key}.xml"
        sitemap = SubElement(sitemapindex, 'sitemap')
        SubElement(sitemap, 'loc').text = loc
        SubElement(sitemap, 'lastmod').text = now
    for key in podcast_sitemaps:
        loc = f"{protocol}://{domain}/sitemap-{key}.xml"
        sitemap = SubElement(sitemapindex, 'sitemap')
        SubElement(sitemap, 'loc').text = loc
        SubElement(sitemap, 'lastmod').text = now
    xml_bytes = tostring(sitemapindex, encoding='utf-8', method='xml')
    return HttpResponse(xml_bytes, content_type='application/xml')

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

def get_episode_sitemaps():
    total = Episode.objects.count()
    num_pages = (total + EPISODE_SITEMAP_PAGE_SIZE - 1) // EPISODE_SITEMAP_PAGE_SIZE
    return {f'episodes-{i+1}': EpisodeSitemap(page=i+1) for i in range(num_pages)}

def get_podcast_sitemaps():
    total = Podcast.objects.count()
    num_pages = (total + PODCAST_SITEMAP_PAGE_SIZE - 1) // PODCAST_SITEMAP_PAGE_SIZE
    return {f'podcasts-{i+1}': PodcastSitemap(page=i+1) for i in range(num_pages)}
