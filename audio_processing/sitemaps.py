from django.contrib.sitemaps import Sitemap
from audio_processing.models import Episode, Podcast

class EpisodeSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.8

    def items(self):
        # Limit to 1000 most recent episodes to avoid memory issues
        return Episode.objects.order_by('-updated_at')[:1000]

    def lastmod(self, obj):
        return obj.updated_at

class PodcastSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        # Limit to 1000 most recent podcasts to avoid memory issues
        return Podcast.objects.order_by('-updated_at')[:1000]

    def lastmod(self, obj):
        return obj.updated_at
