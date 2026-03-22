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
    "trending-shows",
]


def sitemap_index_view(request):
    """Return a sitemap index XML linking to all paginated sitemaps."""
    # Cache the sitemap index for 1 hour to avoid expensive queries on every request
    cache_key = "sitemap_index_xml"
    cached_response = cache.get(cache_key)
    if cached_response:
        return HttpResponse(cached_response, content_type="application/xml")

    domain = getattr(settings, "SITE_DOMAIN", request.get_host())
    protocol = "https" if request.is_secure() else "http"
    sitemapindex = Element(
        "sitemapindex", xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
    )

    # Use cached counts to avoid hitting database on every index request
    episode_count = cache.get_or_set(
        "episode_count", lambda: Episode.objects.count(), 3600
    )
    podcast_count = cache.get_or_set(
        "podcast_count", lambda: Podcast.objects.count(), 3600
    )

    episode_num_pages = min(
        (episode_count + EPISODE_SITEMAP_PAGE_SIZE - 1) // EPISODE_SITEMAP_PAGE_SIZE,
        MAX_SITEMAP_PAGES,
    )
    podcast_num_pages = min(
        (podcast_count + PODCAST_SITEMAP_PAGE_SIZE - 1) // PODCAST_SITEMAP_PAGE_SIZE,
        MAX_SITEMAP_PAGES,
    )

    # Skip lastmod to avoid slow queries - search engines don't require it
    now_iso = timezone.now().isoformat()

    # Add episode sitemap pages
    for i in range(episode_num_pages):
        loc = f"{protocol}://{domain}/sitemap-episodes-{i + 1}.xml"
        sitemap = SubElement(sitemapindex, "sitemap")
        SubElement(sitemap, "loc").text = loc
        SubElement(sitemap, "lastmod").text = now_iso

    # Add podcast sitemap pages
    for i in range(podcast_num_pages):
        loc = f"{protocol}://{domain}/sitemap-podcasts-{i + 1}.xml"
        sitemap = SubElement(sitemapindex, "sitemap")
        SubElement(sitemap, "loc").text = loc
        SubElement(sitemap, "lastmod").text = now_iso

    # Add static pages sitemap
    loc = f"{protocol}://{domain}/sitemap-static.xml"
    sitemap = SubElement(sitemapindex, "sitemap")
    SubElement(sitemap, "loc").text = loc
    SubElement(sitemap, "lastmod").text = now_iso

    xml_bytes = tostring(sitemapindex, encoding="utf-8", method="xml")

    # Cache for 1 hour (3600 seconds)
    cache.set(cache_key, xml_bytes, 3600)

    return HttpResponse(xml_bytes, content_type="application/xml")


def dynamic_sitemap_view(request, section):
    """Dynamically handle episode, podcast, and static sitemap requests."""
    from django.contrib.sitemaps.views import sitemap as sitemap_view

    if section == "static":
        sitemaps = {"static": StaticPageSitemap()}
        return sitemap_view(request, section="static", sitemaps=sitemaps)
    elif section.startswith("episodes-"):
        # Extract page number from section (e.g., 'episodes-1' -> 1)
        try:
            page = int(section.split("-")[1])
            sitemaps = {section: EpisodeSitemap(page=page)}
            return sitemap_view(request, section=section, sitemaps=sitemaps)
        except (ValueError, IndexError):
            return HttpResponse("Not Found", status=404)
    elif section.startswith("podcasts-"):
        # Extract page number from section (e.g., 'podcasts-1' -> 1)
        try:
            page = int(section.split("-")[1])
            sitemaps = {section: PodcastSitemap(page=page)}
            return sitemap_view(request, section=section, sitemaps=sitemaps)
        except (ValueError, IndexError):
            return HttpResponse("Not Found", status=404)
    else:
        return HttpResponse("Not Found", status=404)


class EpisodeSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def __init__(self, page=1):
        self.page = page

    def items(self):
        offset = (self.page - 1) * EPISODE_SITEMAP_PAGE_SIZE
        # Only load essential fields to reduce memory usage
        return Episode.objects.only("id", "slug", "updated_at").order_by("-updated_at")[
            offset : offset + EPISODE_SITEMAP_PAGE_SIZE
        ]

    def location(self, obj):
        return f"/episodes/{obj.slug}" if obj.slug else f"/episodes/{obj.id}"

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
        return Podcast.objects.only("id", "slug", "updated_at").order_by("-updated_at")[
            offset : offset + PODCAST_SITEMAP_PAGE_SIZE
        ]

    def location(self, obj):
        return f"/podcasts/{obj.slug}" if obj.slug else f"/podcasts/{obj.id}"

    def lastmod(self, obj):
        return obj.updated_at


class StaticPageSitemap(Sitemap):
    changefreq = "daily"
    priority = 0.7

    def items(self):
        return STATIC_PAGES

    def location(self, item):
        return f"/{item}"
