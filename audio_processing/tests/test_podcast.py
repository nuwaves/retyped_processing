from unittest.mock import Mock, patch
from datetime import datetime, timedelta, timezone

from django import utils
from django.core.exceptions import ValidationError
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from rest_framework.test import APIClient
from rest_framework import status

from audio_processing.models import Podcast, Episode, Tag


class PodcastModelTest(TestCase):
    """Test cases for the Podcast model."""

    def setUp(self):
        """Set up test data."""
        self.podcast_data = {
            "name": "Test Podcast",
            "url": "https://example.com/feed.xml",
            "description": "A test podcast description",
            "author": "Test Author",
            "language": "en",
            "copyright": "Test Copyright",
            "subtitle": "Test Subtitle",
            "summary": "Test Summary",
            "itunes_explicit": False,
            "itunes_type": "episodic",
            "itunes_keywords": "test,podcast,keywords",
            "itunes_categories": ["Technology", "Business"],
            "image_url": "https://example.com/image.jpg",
            "itunes_image_url": "https://example.com/itunes_image.jpg",
            "owner_name": "Test Owner",
            "owner_email": "test@example.com",
        }

        self.podcast = Podcast.objects.create(**self.podcast_data)

        # Create test tags
        self.tag1 = Tag.objects.create(name="Technology", slug="technology")
        self.tag2 = Tag.objects.create(name="Business", slug="business")

    def test_podcast_creation(self):
        """Test basic podcast creation."""
        self.assertEqual(self.podcast.name, "Test Podcast")
        self.assertEqual(self.podcast.url, "https://example.com/feed.xml")
        self.assertEqual(self.podcast.author, "Test Author")
        self.assertEqual(self.podcast.language, "en")
        self.assertFalse(self.podcast.itunes_explicit)
        self.assertEqual(self.podcast.itunes_categories, ["Technology", "Business"])
        self.assertTrue(self.podcast.is_active)

    def test_podcast_str_method(self):
        """Test the __str__ method."""
        self.assertEqual(str(self.podcast), "Test Podcast")

    def test_podcast_meta_options(self):
        """Test model meta options."""
        self.assertEqual(Podcast._meta.verbose_name, "Podcast")
        self.assertEqual(Podcast._meta.verbose_name_plural, "Podcasts")
        self.assertEqual(Podcast._meta.ordering, ["-created_at"])

    def test_podcast_url_uniqueness(self):
        """Test that podcast URLs must be unique."""
        with self.assertRaises(Exception):  # IntegrityError in practice
            Podcast.objects.create(
                name="Duplicate Podcast", url="https://example.com/feed.xml"  # Same URL
            )

    def test_podcast_optional_fields(self):
        """Test that optional fields can be None/blank."""
        minimal_podcast = Podcast.objects.create(
            name="Minimal Podcast", url="https://example.com/minimal-feed.xml"
        )

        self.assertIsNone(minimal_podcast.description)
        self.assertIsNone(minimal_podcast.author)
        self.assertIsNone(minimal_podcast.subtitle)
        self.assertIsNone(minimal_podcast.pub_date)
        self.assertIsNone(minimal_podcast.last_build_date)

    def test_podcast_tags_relationship(self):
        """Test many-to-many relationship with tags."""
        self.podcast.tags.add(self.tag1, self.tag2)

        self.assertEqual(self.podcast.tags.count(), 2)
        self.assertIn(self.tag1, self.podcast.tags.all())
        self.assertIn(self.tag2, self.podcast.tags.all())

    def test_episode_relationship(self):
        """Test reverse relationship with episodes."""
        episode1 = Episode.objects.create(
            podcast=self.podcast,
            title="Episode 1",
            raw_audio_url="https://example.com/episode1.mp3",
        )
        episode2 = Episode.objects.create(
            podcast=self.podcast,
            title="Episode 2",
            raw_audio_url="https://example.com/episode2.mp3",
        )

        self.assertEqual(self.podcast.episodes.count(), 2)
        self.assertIn(episode1, self.podcast.episodes.all())
        self.assertIn(episode2, self.podcast.episodes.all())


class PodcastFeedProcessingTest(TestCase):
    """Test cases for RSS feed processing functionality."""

    def setUp(self):
        """Set up test data."""
        self.podcast = Podcast.objects.create(
            name="Feed Test Podcast", url="https://example.com/test-feed.xml"
        )

    @patch("audio_processing.models.podcast.feedparser.parse")
    def test_fetch_feed_success(self, mock_parse):
        """Test successful feed fetching."""
        # Mock feed data
        mock_feed = Mock()
        mock_feed.bozo = False
        mock_feed.feed = Mock()
        mock_feed.feed.title = "Updated Podcast Title"
        mock_feed.feed.description = "Updated description"
        mock_feed.feed.language = "en"
        mock_feed.entries = []
        mock_parse.return_value = mock_feed

        # Mock the update_from_feed method to avoid complex mocking
        with patch.object(self.podcast, "update_from_feed") as mock_update:
            result = self.podcast.fetch_feed()

        self.assertIsNotNone(result)
        mock_parse.assert_called_once_with(self.podcast.url)
        mock_update.assert_called_once_with(mock_feed)

    @patch("audio_processing.models.podcast.feedparser.parse")
    def test_fetch_feed_error(self, mock_parse):
        """Test feed fetching with error."""
        mock_parse.side_effect = Exception("Network error")

        result = self.podcast.fetch_feed()

        self.assertIsNone(result)

    @patch("audio_processing.models.podcast.feedparser.parse")
    def test_update_from_feed(self, mock_parse):
        """Test updating podcast metadata from feed."""
        # Create mock feed with comprehensive data
        mock_feed = Mock()
        mock_feed.feed = Mock()
        mock_feed.feed.title = "Updated Title"
        mock_feed.feed.description = "Updated Description"
        mock_feed.feed.language = "fr"
        mock_feed.feed.copyright = "Updated Copyright"
        mock_feed.feed.subtitle = "Updated Subtitle"
        mock_feed.feed.summary = "Updated Summary"
        mock_feed.feed.author = "Updated Author"
        mock_feed.feed.itunes_explicit = "yes"
        mock_feed.feed.itunes_type = "serial"
        mock_feed.feed.itunes_keywords = "updated,keywords"

        # Mock categories
        mock_tag1 = Mock()
        mock_tag1.term = "Technology"
        mock_tag2 = Mock()
        mock_tag2.term = "Science"
        mock_feed.feed.tags = [mock_tag1, mock_tag2]

        # Mock images
        mock_feed.feed.image = Mock()
        mock_feed.feed.image.href = "https://example.com/new-image.jpg"
        mock_feed.feed.itunes_image = Mock()
        mock_feed.feed.itunes_image.href = "https://example.com/new-itunes-image.jpg"

        # Mock owner
        mock_feed.feed.itunes_owner = Mock()
        mock_feed.feed.itunes_owner.itunes_name = "Updated Owner"
        mock_feed.feed.itunes_owner.itunes_email = "updated@example.com"

        self.podcast.update_from_feed(mock_feed)
        self.podcast.refresh_from_db()

        # Verify updates
        self.assertEqual(self.podcast.name, "Updated Title")
        self.assertEqual(self.podcast.description, "Updated Description")
        self.assertEqual(self.podcast.language, "fr")
        self.assertEqual(self.podcast.copyright, "Updated Copyright")
        self.assertEqual(self.podcast.subtitle, "Updated Subtitle")
        self.assertEqual(self.podcast.summary, "Updated Summary")
        self.assertEqual(self.podcast.author, "Updated Author")
        self.assertTrue(self.podcast.itunes_explicit)
        self.assertEqual(self.podcast.itunes_type, "serial")
        self.assertEqual(self.podcast.itunes_keywords, "updated,keywords")
        self.assertEqual(self.podcast.itunes_categories, ["Technology", "Science"])
        self.assertEqual(self.podcast.image_url, "https://example.com/new-image.jpg")
        self.assertEqual(
            self.podcast.itunes_image_url, "https://example.com/new-itunes-image.jpg"
        )
        self.assertEqual(self.podcast.owner_name, "Updated Owner")
        self.assertEqual(self.podcast.owner_email, "updated@example.com")

    def test_create_episode_from_entry(self):
        """Test creating episode from RSS entry."""
        # Mock RSS entry properly
        mock_entry = Mock()
        mock_entry.get = Mock(
            side_effect=lambda key, default=None: {"title": "Test Episode"}.get(
                key, default
            )
        )

        # Mock enclosures (audio files)
        mock_enclosure = Mock()
        mock_enclosure.get = Mock(
            side_effect=lambda key, default=None: {
                "type": "audio/mpeg",
                "href": "https://example.com/episode.mp3",
                "length": "12345678",
            }.get(key, default)
        )

        mock_entry.enclosures = [mock_enclosure]
        mock_entry.summary = "Episode description"
        mock_entry.subtitle = "Episode subtitle"

        # Mock published date
        mock_entry.published_parsed = (2023, 8, 15, 10, 30, 0, 1, 227, 0)

        # Mock content attribute to avoid len() issues
        mock_content = Mock()
        mock_content.get = Mock(return_value="Episode content")
        mock_entry.content = [mock_content]

        # Mock links attribute
        mock_entry.links = []

        # Mock iTunes attributes that might be accessed but set to None/empty
        mock_entry.itunes_episode = None
        mock_entry.itunes_season = None
        mock_entry.itunes_episodetype = None
        mock_entry.itunes_explicit = None
        mock_entry.itunes_keywords = None
        mock_entry.itunes_duration = None

        episode = self.podcast.create_episode_from_entry(mock_entry)

        self.assertIsNotNone(episode)
        self.assertEqual(episode.title, "Test Episode")
        self.assertEqual(episode.podcast, self.podcast)
        self.assertEqual(episode.raw_audio_url, "https://example.com/episode.mp3")
        self.assertEqual(episode.audio_type, "audio/mpeg")
        self.assertEqual(episode.audio_length, 12345678)
        self.assertEqual(episode.description, "Episode description")
        self.assertEqual(episode.subtitle, "Episode subtitle")

    def test_create_episode_from_entry_no_audio(self):
        """Test creating episode when no audio URL found."""
        mock_entry = Mock()
        mock_entry.get = lambda key, default=None: (
            "Test Episode" if key == "title" else default
        )
        mock_entry.enclosures = []
        mock_entry.links = []

        episode = self.podcast.create_episode_from_entry(mock_entry)

        self.assertIsNone(episode)

    def test_process_feed_success(self):
        """Test complete feed processing."""
        # Mock feed with entries
        mock_feed = Mock()
        mock_feed.bozo = False
        mock_feed.feed = Mock()
        mock_feed.feed.title = "Test Podcast"

        # Mock entries
        mock_entry = Mock()
        mock_entry.get = Mock(
            side_effect=lambda key, default=None: {"title": "Episode 1"}.get(
                key, default
            )
        )

        mock_enclosure = Mock()
        mock_enclosure.get = Mock(
            side_effect=lambda key, default=None: {
                "type": "audio/mpeg",
                "href": "https://example.com/episode1.mp3",
            }.get(key, default)
        )

        mock_entry.enclosures = [mock_enclosure]
        mock_entry.summary = "Episode 1 description"

        mock_feed.entries = [mock_entry]

        # Mock the fetch_feed method to return our mock feed
        with patch.object(self.podcast, "fetch_feed") as mock_fetch_feed:
            mock_fetch_feed.return_value = mock_feed

            # Mock the create_episode_from_entry method to return a mock episode
            mock_episode = Mock()
            mock_episode.created_at = utils.timezone.now()

            with patch.object(
                self.podcast, "create_episode_from_entry"
            ) as mock_create_episode:
                mock_create_episode.return_value = mock_episode

                result = self.podcast.process_feed()

                self.assertEqual(result["total_entries"], 1)
                self.assertEqual(result["created"], 1)
                self.assertEqual(result["existing"], 0)
                self.assertEqual(result["failed"], 0)

    def test_process_feed_inactive(self):
        """Test processing inactive feed."""
        self.podcast.is_active = False
        self.podcast.save()

        result = self.podcast.process_feed()

        self.assertIn("error", result)
        self.assertEqual(result["error"], "RSS feed is marked as inactive")

    def test_get_summary(self):
        """Test get_summary method."""
        # Create some episodes
        Episode.objects.create(
            podcast=self.podcast,
            title="Episode 1",
            raw_audio_url="https://example.com/episode1.mp3",
        )
        Episode.objects.create(
            podcast=self.podcast,
            title="Episode 2",
            raw_audio_url="https://example.com/episode2.mp3",
        )

        summary = self.podcast.get_summary()

        self.assertEqual(summary["id"], self.podcast.id)
        self.assertEqual(summary["name"], self.podcast.name)
        self.assertEqual(summary["url"], self.podcast.url)
        self.assertTrue(summary["is_active"])
        self.assertEqual(summary["episode_count"], 2)
        self.assertIsNotNone(summary["created_at"])
        self.assertIsNotNone(summary["updated_at"])


class PodcastDateHandlingTest(TestCase):
    """Test cases for date parsing and handling."""

    def setUp(self):
        self.podcast = Podcast.objects.create(
            name="Date Test Podcast", url="https://example.com/date-test-feed.xml"
        )

    @patch("time.mktime")
    @patch("audio_processing.models.podcast.timezone.get_current_timezone")
    def test_update_from_feed_with_dates(self, mock_get_tz, mock_mktime):
        """Test date parsing in update_from_feed."""
        # Mock timezone and mktime
        mock_get_tz.return_value = timezone.utc
        mock_mktime.return_value = 1692097800.0

        mock_feed = Mock()
        mock_feed.feed = Mock()
        mock_feed.feed.published_parsed = (2023, 8, 15, 10, 30, 0, 1, 227, 0)
        mock_feed.feed.updated_parsed = (2023, 8, 15, 11, 0, 0, 1, 227, 0)

        # Mock or set to None attributes that might cause iteration issues
        mock_feed.feed.title = None
        mock_feed.feed.description = None
        mock_feed.feed.language = None
        mock_feed.feed.copyright = None
        mock_feed.feed.subtitle = None
        mock_feed.feed.summary = None
        mock_feed.feed.author = None
        mock_feed.feed.itunes_explicit = None
        mock_feed.feed.itunes_type = None
        mock_feed.feed.itunes_keywords = None
        mock_feed.feed.tags = []  # Empty list instead of Mock
        mock_feed.feed.image = None
        mock_feed.feed.itunes_image = None
        mock_feed.feed.itunes_owner = None

        self.podcast.update_from_feed(mock_feed)

        self.podcast.refresh_from_db()
        self.assertIsNotNone(self.podcast.pub_date)
        self.assertIsNotNone(self.podcast.last_build_date)


class PodcastValidationTest(TestCase):
    """Test cases for podcast validation."""

    def test_email_field_validation(self):
        """Test email field validation."""
        podcast = Podcast(
            name="Validation Test",
            url="https://example.com/validation-feed.xml",
            owner_email="invalid-email",  # Invalid email
        )

        with self.assertRaises(ValidationError):
            podcast.full_clean()

    def test_url_field_validation(self):
        """Test URL field validation."""
        podcast = Podcast(name="URL Test", url="not-a-valid-url")  # Invalid URL

        with self.assertRaises(ValidationError):
            podcast.full_clean()

    def test_json_field_handling(self):
        """Test JSON field can handle lists and None."""
        podcast = Podcast.objects.create(
            name="JSON Test",
            url="https://example.com/json-feed.xml",
            itunes_categories=["Tech", "Business"],  # List
        )

        self.assertEqual(podcast.itunes_categories, ["Tech", "Business"])

        # Test None value
        podcast.itunes_categories = None
        podcast.save()
        podcast.refresh_from_db()
        self.assertIsNone(podcast.itunes_categories)


class PodcastViewSetTest(TestCase):
    """Test cases for the podcast API endpoints."""

    def setUp(self):
        """Set up test data."""
        self.client = APIClient()

        # Create test user
        self.user = User.objects.create_user(
            username="testuser", email="test@example.com", password="testpass"
        )
        self.client.force_authenticate(user=self.user)

        # Create test data
        self.podcast = Podcast.objects.create(
            name="Test Podcast",
            url="https://example.com/feed.xml",
            description="A podcast for testing",
            author="Test Author",
        )

    def test_list_podcasts(self):
        """Test listing all podcasts."""
        url = reverse("v1:api-v1-podcasts-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["name"], self.podcast.name)

    def test_retrieve_podcast(self):
        """Test retrieving a single podcast."""
        url = reverse("v1:api-v1-podcasts-retrieve", kwargs={"pk": self.podcast.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        data = response.json()

        self.assertEqual(data["name"], self.podcast.name)
        self.assertEqual(data["url"], self.podcast.url)
        self.assertEqual(data["description"], self.podcast.description)
        self.assertEqual(data["author"], self.podcast.author)

    def test_list_podcasts_unauthenticated(self):
        """Test that unauthenticated requests can list podcasts."""
        self.client.force_authenticate(user=None)

        url = reverse("v1:api-v1-podcasts-list")
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_podcast_unauthenticated(self):
        """Test that unauthenticated requests can retrieve a podcast."""
        self.client.force_authenticate(user=None)

        url = reverse("v1:api-v1-podcasts-retrieve", kwargs={"pk": self.podcast.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
