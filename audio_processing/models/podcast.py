from django.db import models
from django.utils import timezone
import feedparser
import logging

logger = logging.getLogger(__name__)


class Podcast(models.Model):
    # Basic info
    name = models.CharField(max_length=1000, help_text="Friendly name for the podcast")
    url = models.URLField(unique=True, help_text="RSS feed URL")
    description = models.TextField(blank=True, null=True, help_text="Description of the podcast")
    
    # RSS metadata
    subtitle = models.CharField(max_length=500, blank=True, null=True, help_text="iTunes subtitle")
    summary = models.TextField(blank=True, null=True, help_text="iTunes summary (longer description)")
    author = models.CharField(max_length=200, blank=True, null=True, help_text="Podcast author/creator")
    language = models.CharField(max_length=10, blank=True, null=True, help_text="Language code (e.g., 'en')")
    copyright = models.CharField(max_length=200, blank=True, null=True, help_text="Copyright information")
    
    # iTunes specific fields
    itunes_explicit = models.BooleanField(default=False, help_text="iTunes explicit content flag")
    itunes_type = models.CharField(max_length=20, blank=True, null=True, help_text="iTunes podcast type (episodic/serial)")
    itunes_keywords = models.CharField(max_length=500, blank=True, null=True, help_text="iTunes keywords")
    itunes_categories = models.JSONField(blank=True, null=True, help_text="iTunes categories as JSON")
    
    # Images
    image_url = models.URLField(max_length=500, blank=True, null=True, help_text="Podcast artwork URL")
    itunes_image_url = models.URLField(max_length=500, blank=True, null=True, help_text="iTunes specific image URL")
    
    # Owner information
    owner_name = models.CharField(max_length=200, blank=True, null=True, help_text="Owner name")
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
        
        # iTunes specific fields
        if hasattr(feed_info, 'subtitle') and feed_info.subtitle:
            self.subtitle = feed_info.subtitle
        
        if hasattr(feed_info, 'summary') and feed_info.summary:
            self.summary = feed_info.summary
        
        if hasattr(feed_info, 'author') and feed_info.author:
            self.author = feed_info.author
        
        # iTunes metadata
        if hasattr(feed_info, 'itunes_explicit'):
            self.itunes_explicit = feed_info.itunes_explicit == 'yes'
        
        if hasattr(feed_info, 'itunes_type') and feed_info.itunes_type:
            self.itunes_type = feed_info.itunes_type
        
        if hasattr(feed_info, 'itunes_keywords') and feed_info.itunes_keywords:
            self.itunes_keywords = feed_info.itunes_keywords
        
        # Categories
        if hasattr(feed_info, 'tags') and feed_info.tags:
            categories = []
            for tag in feed_info.tags:
                if hasattr(tag, 'term'):
                    categories.append(tag.term)
            if categories:
                self.itunes_categories = categories
        
        # Images
        if hasattr(feed_info, 'image') and hasattr(feed_info.image, 'href'):
            self.image_url = feed_info.image.href
        
        if hasattr(feed_info, 'itunes_image') and hasattr(feed_info.itunes_image, 'href'):
            self.itunes_image_url = feed_info.itunes_image.href
        
        # Owner information
        if hasattr(feed_info, 'itunes_owner'):
            if hasattr(feed_info.itunes_owner, 'itunes_name'):
                self.owner_name = feed_info.itunes_owner.itunes_name
            if hasattr(feed_info.itunes_owner, 'itunes_email'):
                self.owner_email = feed_info.itunes_owner.itunes_email
        
        # Dates
        if hasattr(feed_info, 'published_parsed') and feed_info.published_parsed:
            try:
                import time
                from datetime import datetime
                timestamp = time.mktime(feed_info.published_parsed)
                self.pub_date = datetime.fromtimestamp(timestamp, tz=timezone.get_current_timezone())
            except Exception as e:
                logger.warning(f"Failed to parse pub_date: {str(e)}")
        
        if hasattr(feed_info, 'updated_parsed') and feed_info.updated_parsed:
            try:
                import time
                from datetime import datetime
                timestamp = time.mktime(feed_info.updated_parsed)
                self.last_build_date = datetime.fromtimestamp(timestamp, tz=timezone.get_current_timezone())
            except Exception as e:
                logger.warning(f"Failed to parse last_build_date: {str(e)}")
        
        self.save()
        logger.info(f"Updated podcast metadata: {self.name}")
    
    def create_episode_from_entry(self, entry):
        """
        Creates a podcast episode from an RSS entry.
        Returns the created/existing Episode object or None if failed.
        """
        # Import here to avoid circular imports
        from .episode import Episode
        
        title = entry.get('title', 'No Title')
        logger.info(f"Processing episode entry: {title}")
        
        # Extract audio URL and metadata from enclosures
        audio_url = None
        audio_type = None
        audio_length = None
        
        if hasattr(entry, 'enclosures') and entry.enclosures:
            for enclosure in entry.enclosures:
                if enclosure.get('type', '').startswith('audio/'):
                    audio_url = enclosure.get('href')
                    audio_type = enclosure.get('type')
                    audio_length = enclosure.get('length')
                    if audio_length:
                        try:
                            audio_length = int(audio_length)
                        except (ValueError, TypeError):
                            audio_length = None
                    break
        
        # Fallback: check for links that might be audio files
        if not audio_url and hasattr(entry, 'links'):
            for link in entry.links:
                if link.get('type', '').startswith('audio/'):
                    audio_url = link.get('href')
                    audio_type = link.get('type')
                    break
        
        if not audio_url:
            logger.warning(f"No audio URL found for entry: {title}")
            return None
        
        # Extract dates
        release_date = None
        pub_date = None
        
        if hasattr(entry, 'published_parsed') and entry.published_parsed:
            try:
                import time
                from datetime import datetime
                timestamp = time.mktime(entry.published_parsed)
                pub_date = datetime.fromtimestamp(timestamp, tz=timezone.get_current_timezone())
                release_date = pub_date  # Use pub_date as release_date for backward compatibility
            except Exception as e:
                logger.warning(f"Failed to parse published date for entry '{title}': {str(e)}")
        
        # Fallback: try 'updated_parsed' if 'published_parsed' is not available
        if not release_date and hasattr(entry, 'updated_parsed') and entry.updated_parsed:
            try:
                import time
                from datetime import datetime
                timestamp = time.mktime(entry.updated_parsed)
                release_date = datetime.fromtimestamp(timestamp, tz=timezone.get_current_timezone())
                if not pub_date:
                    pub_date = release_date
            except Exception as e:
                logger.warning(f"Failed to parse updated date for entry '{title}': {str(e)}")
        
        # Check if episode already exists
        existing_episode = Episode.objects.filter(raw_audio_url=audio_url).first()
        if existing_episode:
            # Update missing fields
            updated = self._update_existing_episode(existing_episode, entry, title, audio_type, audio_length, release_date, pub_date)
            if updated:
                logger.info(f"Updated existing episode: {title}")
            return existing_episode
        
        # Create new episode with all the rich metadata
        episode_data = {
            'podcast': self,
            'title': title,
            'raw_audio_url': audio_url,
            'audio_type': audio_type,
            'audio_length': audio_length,
            'release_date': release_date,
            'pub_date': pub_date,
        }
        
        # Add optional fields from entry
        if hasattr(entry, 'summary') and entry.summary:
            episode_data['description'] = entry.summary
        
        if hasattr(entry, 'subtitle') and entry.subtitle:
            episode_data['subtitle'] = entry.subtitle
        
        if hasattr(entry, 'itunes_episode') and entry.itunes_episode:
            try:
                episode_data['episode_number'] = int(entry.itunes_episode)
            except (ValueError, TypeError):
                pass
        
        if hasattr(entry, 'itunes_season') and entry.itunes_season:
            try:
                episode_data['season_number'] = int(entry.itunes_season)
            except (ValueError, TypeError):
                pass
        
        if hasattr(entry, 'itunes_episodetype') and entry.itunes_episodetype:
            episode_data['episode_type'] = entry.itunes_episodetype
        
        if hasattr(entry, 'itunes_explicit'):
            episode_data['itunes_explicit'] = entry.itunes_explicit == 'yes'
        
        if hasattr(entry, 'itunes_keywords') and entry.itunes_keywords:
            episode_data['itunes_keywords'] = entry.itunes_keywords
        
        if hasattr(entry, 'content') and entry.content:
            # Get the first content item (usually HTML)
            if len(entry.content) > 0:
                episode_data['content_encoded'] = entry.content[0].get('value', '')
        
        if hasattr(entry, 'itunes_duration') and entry.itunes_duration:
            try:
                # Parse duration (format: HH:MM:SS or MM:SS or seconds)
                duration_str = entry.itunes_duration
                parts = duration_str.split(':')
                if len(parts) == 3:  # HH:MM:SS
                    hours, minutes, seconds = map(int, parts)
                    total_seconds = hours * 3600 + minutes * 60 + seconds
                elif len(parts) == 2:  # MM:SS
                    minutes, seconds = map(int, parts)
                    total_seconds = minutes * 60 + seconds
                else:  # Just seconds
                    total_seconds = int(duration_str)
                
                from datetime import timedelta
                episode_data['duration'] = timedelta(seconds=total_seconds)
            except (ValueError, TypeError):
                pass
        
        episode = Episode.objects.create(**episode_data)
        logger.info(f"Created episode: {title} - {audio_url} (released: {release_date})")
        return episode
    
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
            result = self.create_episode_from_entry(entry)
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
