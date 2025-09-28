from django.db import models
from django.utils import timezone
import feedparser
import logging
from audio_processing.models.mixins import (
    SearchableMixin,
)
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class Podcast(models.Model, SearchableMixin):
    slug = models.SlugField(max_length=255, unique=True, blank=True, help_text="Unique slug for podcast")
    # Search configuration
    SEARCH_INDEX_UID = 'podcasts'
    
    # Basic info
    name = models.CharField(max_length=1000, help_text="Friendly name for the podcast")
    url = models.URLField(unique=True, help_text="RSS feed URL")
    description = models.TextField(blank=True, null=True, help_text="Description of the podcast")
    
    # RSS metadata
    subtitle = models.CharField(max_length=5000, blank=True, null=True, help_text="iTunes subtitle")
    summary = models.TextField(blank=True, null=True, help_text="iTunes summary (longer description)")
    author = models.CharField(max_length=2000, blank=True, null=True, help_text="Podcast author/creator")
    language = models.CharField(max_length=10, blank=True, null=True, help_text="Language code (e.g., 'en')")
    copyright = models.CharField(max_length=2000, blank=True, null=True, help_text="Copyright information")
    
    # iTunes specific fields
    itunes_explicit = models.BooleanField(default=False, help_text="iTunes explicit content flag")
    itunes_type = models.CharField(max_length=20, blank=True, null=True, help_text="iTunes podcast type (episodic/serial)")
    itunes_categories = models.JSONField(blank=True, null=True, help_text="iTunes categories as JSON")
    
    # Images
    image_url = models.URLField(max_length=500, blank=True, null=True, help_text="Podcast artwork URL")
    itunes_image_url = models.URLField(max_length=500, blank=True, null=True, help_text="iTunes specific image URL")
    
    # Owner information
    owner_name = models.CharField(max_length=2000, blank=True, null=True, help_text="Owner name")
    owner_email = models.EmailField(blank=True, null=True, help_text="Owner email")
    
    # Dates
    pub_date = models.DateTimeField(blank=True, null=True, help_text="Last publication date from RSS")
    last_build_date = models.DateTimeField(blank=True, null=True, help_text="Last build date from RSS")
    
    # System fields
    is_active = models.BooleanField(default=True, help_text="Whether to actively process this podcast")
    last_processed = models.DateTimeField(blank=True, null=True, help_text="Last time this podcast was processed")
    tags = models.ManyToManyField('Tag', blank=True, related_name='podcasts', help_text="Tags associated with this RSS feed")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Podcast"
        verbose_name_plural = "Podcasts"
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        from django.utils.text import slugify
        if not self.slug and self.name:
            base_slug = slugify(self.name)
            slug = base_slug
            # Ensure uniqueness
            counter = 1
            while Podcast.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)
    
    def fetch_feed(self):
        """
        Fetch and parse the RSS feed and update metadata.
        Returns the parsed feed object or None if failed.
        """
        logger.info(f"Fetching RSS feed: {self.url}")
        try:
            feed = feedparser.parse(self.url)
            
            if feed.bozo:
                logger.warning(f"Feed has parsing issues: {self.url}")
                if hasattr(feed, 'bozo_exception'):
                    logger.warning(f"Bozo exception: {feed.bozo_exception}")
            
            # Update podcast metadata from feed
            self.update_from_feed(feed)
            
            return feed
        except Exception as e:
            logger.error(f"Failed to fetch feed {self.url}: {str(e)}")
            return None
    
    def update_from_feed(self, feed):
        """
        Update podcast metadata from parsed RSS feed.
        """
        if not hasattr(feed, 'feed'):
            return
        
        feed_info = feed.feed

        # Basic information
        if hasattr(feed_info, 'title') and feed_info.title:
            self.name = feed_info.title
        
        if hasattr(feed_info, 'description') and feed_info.description:
            self.description = feed_info.description
        
        if hasattr(feed_info, 'language') and feed_info.language:
            self.language = feed_info.language
        
        if hasattr(feed_info, 'copyright') and feed_info.copyright:
            self.copyright = feed_info.copyright
        
        # iTunes specific fields - feedparser converts itunes: namespace to attributes
        # Try both direct access and iTunes-specific attribute names
        if hasattr(feed_info, 'itunes_subtitle') and feed_info.itunes_subtitle:
            self.subtitle = feed_info.itunes_subtitle
        elif hasattr(feed_info, 'subtitle') and feed_info.subtitle:
            self.subtitle = feed_info.subtitle
        
        if hasattr(feed_info, 'itunes_summary') and feed_info.itunes_summary:
            self.summary = feed_info.itunes_summary
        elif hasattr(feed_info, 'summary') and feed_info.summary:
            self.summary = feed_info.summary
        
        if hasattr(feed_info, 'itunes_author') and feed_info.itunes_author:
            self.author = feed_info.itunes_author
        elif hasattr(feed_info, 'author') and feed_info.author:
            self.author = feed_info.author

        # iTunes metadata - these are namespace-specific
        if hasattr(feed_info, 'itunes_explicit'):
            self.itunes_explicit = feed_info.itunes_explicit == 'yes'
        
        if hasattr(feed_info, 'itunes_type') and feed_info.itunes_type:
            self.itunes_type = feed_info.itunes_type
        
        if hasattr(feed_info, 'itunes_keywords') and feed_info.itunes_keywords:
            self.itunes_keywords = feed_info.itunes_keywords

        if hasattr(feed_info, 'transcript') and feed_info.transcript:
            self.has_public_transcript = True

        # Categories
        if hasattr(feed_info, 'tags') and feed_info.tags:
            itunes_keywords = [tag.term for tag in feed_info.tags if hasattr(tag, 'term')]
            self._process_itunes_keywords_as_tags(itunes_keywords)
        
        # Images - handle both standard and iTunes image formats
        if hasattr(feed_info, 'image'):
            if hasattr(feed_info.image, 'href'):
                self.image_url = feed_info.image.href
            elif hasattr(feed_info.image, 'url'):
                self.image_url = feed_info.image.url
        
        if hasattr(feed_info, 'itunes_image'):
            if hasattr(feed_info.itunes_image, 'href'):
                self.itunes_image_url = feed_info.itunes_image.href
            elif hasattr(feed_info.itunes_image, 'url'):
                self.itunes_image_url = feed_info.itunes_image.url
        
        # Owner information
        if hasattr(feed_info, 'itunes_owner'):
            if hasattr(feed_info.itunes_owner, 'itunes_name'):
                self.owner_name = feed_info.itunes_owner.itunes_name
            if hasattr(feed_info.itunes_owner, 'itunes_email'):
                self.owner_email = feed_info.itunes_owner.itunes_email
        
        # Dates
        if hasattr(feed_info, 'published_parsed') and feed_info.published_parsed:
            try:
                timestamp = time.mktime(feed_info.published_parsed)
                self.pub_date = datetime.fromtimestamp(timestamp, tz=timezone.get_current_timezone())
            except Exception as e:
                logger.warning(f"Failed to parse pub_date: {str(e)}")
        
        if hasattr(feed_info, 'updated_parsed') and feed_info.updated_parsed:
            try:
                timestamp = time.mktime(feed_info.updated_parsed)
                self.last_build_date = datetime.fromtimestamp(timestamp, tz=timezone.get_current_timezone())
            except Exception as e:
                logger.warning(f"Failed to parse last_build_date: {str(e)}")
        
        self.save()
        logger.info(f"Updated podcast metadata: {self.name}")
        
        # Debug: Log available attributes to help with troubleshooting
        self._debug_feed_attributes(feed_info)
    
    def _debug_feed_attributes(self, feed_info):
        """Debug method to log available feed attributes."""
        logger.debug(f"Available feed attributes for {self.name}:")
        
        # Get all attributes that contain 'itunes'
        itunes_attrs = [attr for attr in dir(feed_info) if 'itunes' in attr.lower() and not attr.startswith('_')]
        if itunes_attrs:
            logger.debug(f"iTunes attributes found: {itunes_attrs}")
        else:
            logger.debug("No iTunes attributes found")
        
        # Check for common attributes
        common_attrs = ['title', 'subtitle', 'summary', 'author', 'description', 'language', 'image']
        for attr in common_attrs:
            if hasattr(feed_info, attr):
                value = getattr(feed_info, attr)
                logger.debug(f"{attr}: {type(value)} - {str(value)[:100] if value else 'None'}...")
        
        # Special handling for tags/categories
        if hasattr(feed_info, 'tags'):
            logger.debug(f"Tags found: {len(feed_info.tags) if feed_info.tags else 0}")
            if feed_info.tags:
                for i, tag in enumerate(feed_info.tags[:3]):  # Show first 3 tags
                    logger.debug(f"  Tag {i}: {tag}")
    
    
    def _update_existing_episode(self, episode, entry, title, audio_type, audio_length, release_date, pub_date):
        """Helper method to update existing episode with missing data"""
        
        # Update basic fields
        if title:
            episode.title = title
        
        if audio_type:
            episode.audio_type = audio_type
            
        if audio_length:
            episode.audio_length = audio_length
        
        if release_date:
            episode.release_date = release_date
            
        if pub_date:
            episode.pub_date = pub_date
        
        # Update description
        if hasattr(entry, 'summary') and entry.summary:
            episode.description = entry.summary
        
        # Update subtitle
        if hasattr(entry, 'subtitle') and entry.subtitle:
            episode.subtitle = entry.subtitle
        
        episode.save()
        return True

    def process_feed(self):
        """
        Process this RSS feed and create episodes for all entries.
        Returns a summary of the processing results.
        """
        from audio_processing.models import Episode

        if not self.is_active:
            logger.info(f"RSS feed is inactive: {self.url}")
            return {'error': "RSS feed is marked as inactive"}
        
        feed = self.fetch_feed()
        if not feed:
            return {'error': "Failed to fetch feed"}
        
        if not hasattr(feed, 'entries') or not feed.entries:
            logger.warning(f"No entries found in feed: {self.url}")
            return {'error': "No entries found in feed"}
        
        created_count = 0
        existing_count = 0
        failed_count = 0
        
        for entry in feed.entries:
            result = Episode.create_from_entry(self, entry)
            if result is None:
                failed_count += 1
            elif result:
                # Check if this was a new creation
                if result.created_at >= timezone.now() - timezone.timedelta(seconds=1):
                    created_count += 1
                else:
                    existing_count += 1
        
        # Update last_processed timestamp
        self.last_processed = timezone.now()
        self.save()
        
        summary = {
            'total_entries': len(feed.entries),
            'created': created_count,
            'existing': existing_count,
            'failed': failed_count,
            'rss_feed_id': self.id,
            'rss_feed_name': self.name
        }
        
        logger.info(f"RSS feed processing complete: {summary}")
        return summary
    
    def get_summary(self):
        """
        Get summary information about this RSS feed and its podcasts.
        """
        episode_count = self.episodes.count()
        
        return {
            'id': self.id,
            'name': self.name,
            'url': self.url,
            'is_active': self.is_active,
            'last_processed': self.last_processed,
            'episode_count': episode_count,
            'created_at': self.created_at,
            'updated_at': self.updated_at
        }

    def _process_itunes_keywords_as_tags(self, itunes_keywords):
        """
        Process iTunes keywords and create/add them as tags to this podcast.
        Keywords are typically comma-separated in the iTunes keywords field.
        """
        if not itunes_keywords:
            return
        
        # Import Tag model here to avoid circular imports
        from .tag import Tag
        
        # Process each keyword
        added_tags = []
        for keyword in itunes_keywords:
            if not keyword or len(keyword) > 100:  # Skip empty or too long keywords
                continue
                
            try:
                # Get or create tag
                tag, created = Tag.objects.get_or_create(
                    name=keyword,
                    defaults={
                        'slug': self._generate_slug_from_keyword(keyword),
                        'description': f'Auto-generated tag from iTunes keywords'
                    }
                )
                
                # Add tag to podcast if not already present
                if not self.tags.filter(id=tag.id).exists():
                    self.tags.add(tag)
                    added_tags.append(tag.name)
                    
                    if created:
                        logger.info(f"Created new tag: {tag.name}")
                    else:
                        logger.info(f"Added existing tag: {tag.name}")
                        
            except Exception as e:
                logger.error(f"Failed to process keyword '{keyword}' as tag: {str(e)}")
                continue
        
        if added_tags:
            logger.info(f"Added {len(added_tags)} tags to podcast '{self.name}': {', '.join(added_tags)}")
        else:
            logger.info(f"No new tags were added to podcast '{self.name}'")

    def _generate_slug_from_keyword(self, keyword):
        """
        Generate a URL-friendly slug from a keyword.
        """
        import re
        from django.utils.text import slugify
        
        # Use Django's slugify to create a URL-friendly slug
        slug = slugify(keyword)
        
        # If slugify returns empty (e.g., for non-ASCII characters), 
        # create a basic slug by removing non-alphanumeric characters
        if not slug:
            slug = re.sub(r'[^a-zA-Z0-9\s-]', '', keyword.lower())
            slug = re.sub(r'[\s-]+', '-', slug).strip('-')
        
        # Ensure slug is not empty and not too long
        if not slug:
            slug = 'tag'
        
        slug = slug[:50]  # Limit length
        
        return slug
    def get_search_document(self):
        """
        Prepare podcast data for search indexing.
        
        Returns:
            dict: Document data to be indexed, or None if not indexable
        """
        # Check if we have minimum required data
        if not self.name or not self.name.strip():
            logger.warning(f"No name available for podcast search indexing: {self.url}")
            return None
        
        # Prepare document data
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description or "",
            "subtitle": self.subtitle or "",
            "summary": self.summary or "",
            "author": self.author or "",
            "language": self.language or "",
            "itunes_categories": self.itunes_categories or [],
            "url": self.url,
            "image_url": self.image_url or "",
            "owner_name": self.owner_name or "",
            "owner_email": self.owner_email or "",
            "pub_date": self.pub_date.isoformat() if self.pub_date else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "is_active": self.is_active,
            "episode_count": self.episodes.count(),
            "tags": [tag.name for tag in self.tags.all()]
        }

    def get_absolute_url(self):
        return '/shows/' + self.slug