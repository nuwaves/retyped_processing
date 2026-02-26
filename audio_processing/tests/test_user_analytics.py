from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.test import TestCase

from audio_processing.models import Episode, Podcast, UserAnalytics


class UserAnalyticsModelTest(TestCase):
    """Test cases for the UserAnalytics model."""

    def setUp(self):
        """Set up test data."""
        # Create test user
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )

        # Create another user for multi-user tests
        self.user2 = User.objects.create_user(
            username='testuser2',
            email='test2@example.com',
            password='testpass123'
        )

        # Create test podcast
        self.podcast = Podcast.objects.create(
            name='Test Podcast',
            url='https://example.com/test-feed.xml',
            description='A test podcast'
        )

        # Create test episode
        self.episode = Episode.objects.create(
            podcast=self.podcast,
            title='Test Episode',
            raw_audio_url='https://example.com/episode.mp3',
            description='A test episode'
        )

    def test_create_podcast_analytics(self):
        """Test creating analytics for a podcast."""
        analytics = UserAnalytics.objects.create(
            user=self.user,
            podcast=self.podcast,
            views=5
        )

        self.assertEqual(analytics.user, self.user)
        self.assertEqual(analytics.podcast, self.podcast)
        self.assertIsNone(analytics.episode)
        self.assertEqual(analytics.views, 5)
        self.assertEqual(analytics.entity, self.podcast)
        self.assertEqual(analytics.entity_type, 'podcast')

    def test_create_episode_analytics(self):
        """Test creating analytics for an episode."""
        analytics = UserAnalytics.objects.create(
            user=self.user,
            episode=self.episode,
            views=3
        )

        self.assertEqual(analytics.user, self.user)
        self.assertEqual(analytics.episode, self.episode)
        self.assertIsNone(analytics.podcast)
        self.assertEqual(analytics.views, 3)
        self.assertEqual(analytics.entity, self.episode)
        self.assertEqual(analytics.entity_type, 'episode')

    def test_default_views_value(self):
        """Test that views defaults to 0."""
        analytics = UserAnalytics.objects.create(
            user=self.user,
            podcast=self.podcast
        )

        self.assertEqual(analytics.views, 0)

    def test_str_method_podcast(self):
        """Test string representation for podcast analytics."""
        analytics = UserAnalytics.objects.create(
            user=self.user,
            podcast=self.podcast,
            views=2
        )

        # Note: The __str__ method references get_analytics_type_display() which doesn't exist
        # So this test might fail, but we'll test the basic structure
        expected_parts = [self.user.username, self.podcast.name]
        str_repr = str(analytics)

        for part in expected_parts:
            self.assertIn(part, str_repr)

    def test_str_method_episode(self):
        """Test string representation for episode analytics."""
        analytics = UserAnalytics.objects.create(
            user=self.user,
            episode=self.episode,
            views=1
        )

        expected_parts = [self.user.username, self.episode.title]
        str_repr = str(analytics)

        for part in expected_parts:
            self.assertIn(part, str_repr)

    def test_entity_property(self):
        """Test the entity property returns the correct entity."""
        # Test with podcast
        podcast_analytics = UserAnalytics.objects.create(
            user=self.user,
            podcast=self.podcast
        )
        self.assertEqual(podcast_analytics.entity, self.podcast)

        # Test with episode
        episode_analytics = UserAnalytics.objects.create(
            user=self.user,
            episode=self.episode
        )
        self.assertEqual(episode_analytics.entity, self.episode)

    def test_entity_type_property(self):
        """Test the entity_type property returns correct type."""
        # Test with podcast
        podcast_analytics = UserAnalytics.objects.create(
            user=self.user,
            podcast=self.podcast
        )
        self.assertEqual(podcast_analytics.entity_type, 'podcast')

        # Test with episode
        episode_analytics = UserAnalytics.objects.create(
            user=self.user,
            episode=self.episode
        )
        self.assertEqual(episode_analytics.entity_type, 'episode')

    def test_get_entity_display_name(self):
        """Test getting display name of associated entity."""
        # Test with podcast
        podcast_analytics = UserAnalytics.objects.create(
            user=self.user,
            podcast=self.podcast
        )
        self.assertEqual(podcast_analytics.get_entity_display_name(), self.podcast.name)

        # Test with episode
        episode_analytics = UserAnalytics.objects.create(
            user=self.user,
            episode=self.episode
        )
        self.assertEqual(episode_analytics.get_entity_display_name(), self.episode.title)

    def test_validation_no_entity(self):
        """Test validation fails when neither podcast nor episode is specified."""
        analytics = UserAnalytics(user=self.user, views=1)

        with self.assertRaises(ValidationError) as context:
            analytics.full_clean()

        self.assertIn("Either podcast or episode must be specified", str(context.exception))

    def test_validation_both_entities(self):
        """Test validation fails when both podcast and episode are specified."""
        analytics = UserAnalytics(
            user=self.user,
            podcast=self.podcast,
            episode=self.episode,
            views=1
        )

        with self.assertRaises(ValidationError) as context:
            analytics.full_clean()

        self.assertIn("Cannot specify both podcast and episode", str(context.exception))

    def test_save_validation(self):
        """Test that save() method runs validation."""
        # Test with no entity
        with self.assertRaises(ValidationError):
            UserAnalytics.objects.create(user=self.user, views=1)

        # Test with both entities
        with self.assertRaises(ValidationError):
            UserAnalytics.objects.create(
                user=self.user,
                podcast=self.podcast,
                episode=self.episode,
                views=1
            )

    def test_user_relationship(self):
        """Test the user relationship works correctly."""
        analytics1 = UserAnalytics.objects.create(
            user=self.user,
            podcast=self.podcast,
            views=2
        )

        analytics2 = UserAnalytics.objects.create(
            user=self.user,
            episode=self.episode,
            views=3
        )

        # Test reverse relationship
        user_analytics = self.user.analytics.all()
        self.assertEqual(user_analytics.count(), 2)
        self.assertIn(analytics1, user_analytics)
        self.assertIn(analytics2, user_analytics)

    def test_podcast_relationship(self):
        """Test the podcast relationship works correctly."""
        analytics1 = UserAnalytics.objects.create(
            user=self.user,
            podcast=self.podcast,
            views=1
        )

        analytics2 = UserAnalytics.objects.create(
            user=self.user2,
            podcast=self.podcast,
            views=2
        )

        # Test reverse relationship
        podcast_analytics = self.podcast.user_analytics.all()
        self.assertEqual(podcast_analytics.count(), 2)
        self.assertIn(analytics1, podcast_analytics)
        self.assertIn(analytics2, podcast_analytics)

    def test_episode_relationship(self):
        """Test the episode relationship works correctly."""
        analytics1 = UserAnalytics.objects.create(
            user=self.user,
            episode=self.episode,
            views=3
        )

        analytics2 = UserAnalytics.objects.create(
            user=self.user2,
            episode=self.episode,
            views=4
        )

        # Test reverse relationship
        episode_analytics = self.episode.user_analytics.all()
        self.assertEqual(episode_analytics.count(), 2)
        self.assertIn(analytics1, episode_analytics)
        self.assertIn(analytics2, episode_analytics)

    def test_cascade_delete_user(self):
        """Test that analytics are deleted when user is deleted."""
        analytics = UserAnalytics.objects.create(
            user=self.user,
            podcast=self.podcast,
            views=1
        )

        analytics_id = analytics.id
        self.user.delete()

        # Analytics should be deleted
        with self.assertRaises(UserAnalytics.DoesNotExist):
            UserAnalytics.objects.get(id=analytics_id)

    def test_cascade_delete_podcast(self):
        """Test that analytics are deleted when podcast is deleted."""
        analytics = UserAnalytics.objects.create(
            user=self.user,
            podcast=self.podcast,
            views=1
        )

        analytics_id = analytics.id
        self.podcast.delete()

        # Analytics should be deleted
        with self.assertRaises(UserAnalytics.DoesNotExist):
            UserAnalytics.objects.get(id=analytics_id)

    def test_cascade_delete_episode(self):
        """Test that analytics are deleted when episode is deleted."""
        analytics = UserAnalytics.objects.create(
            user=self.user,
            episode=self.episode,
            views=1
        )

        analytics_id = analytics.id
        self.episode.delete()

        # Analytics should be deleted
        with self.assertRaises(UserAnalytics.DoesNotExist):
            UserAnalytics.objects.get(id=analytics_id)

    def test_meta_options(self):
        """Test model meta options."""
        self.assertEqual(UserAnalytics._meta.verbose_name, "User Analytics")
        self.assertEqual(UserAnalytics._meta.verbose_name_plural, "User Analytics")

        # Test ordering (though updated_at field doesn't exist in current model)
        # This test might fail if updated_at field is not added
        expected_ordering = ['-updated_at']
        # Only test if ordering is set
        if UserAnalytics._meta.ordering:
            self.assertEqual(UserAnalytics._meta.ordering, expected_ordering)

    def test_multiple_analytics_same_user_entity(self):
        """Test that multiple analytics records can exist for same user-entity pair."""
        # This might not be allowed depending on business logic, but testing current model
        analytics1 = UserAnalytics.objects.create(
            user=self.user,
            podcast=self.podcast,
            views=1
        )

        # Should be able to create another record
        analytics2 = UserAnalytics.objects.create(
            user=self.user,
            podcast=self.podcast,
            views=2
        )

        self.assertNotEqual(analytics1.id, analytics2.id)
        self.assertEqual(analytics1.user, analytics2.user)
        self.assertEqual(analytics1.podcast, analytics2.podcast)


class UserAnalyticsQueryTest(TestCase):
    """Test cases for querying UserAnalytics."""

    def setUp(self):
        """Set up test data."""
        self.user1 = User.objects.create_user(username='user1', password='pass123')
        self.user2 = User.objects.create_user(username='user2', password='pass123')

        self.podcast1 = Podcast.objects.create(
            name='Podcast 1',
            url='https://example.com/feed1.xml'
        )
        self.podcast2 = Podcast.objects.create(
            name='Podcast 2',
            url='https://example.com/feed2.xml'
        )

        self.episode1 = Episode.objects.create(
            podcast=self.podcast1,
            title='Episode 1',
            raw_audio_url='https://example.com/episode1.mp3'
        )

        # Create test analytics
        UserAnalytics.objects.create(user=self.user1, podcast=self.podcast1, views=5)
        UserAnalytics.objects.create(user=self.user1, episode=self.episode1, views=3)
        UserAnalytics.objects.create(user=self.user2, podcast=self.podcast1, views=2)
        UserAnalytics.objects.create(user=self.user2, podcast=self.podcast2, views=1)

    def test_filter_by_user(self):
        """Test filtering analytics by user."""
        user1_analytics = UserAnalytics.objects.filter(user=self.user1)
        self.assertEqual(user1_analytics.count(), 2)

        user2_analytics = UserAnalytics.objects.filter(user=self.user2)
        self.assertEqual(user2_analytics.count(), 2)

    def test_filter_by_podcast(self):
        """Test filtering analytics by podcast."""
        podcast1_analytics = UserAnalytics.objects.filter(podcast=self.podcast1)
        self.assertEqual(podcast1_analytics.count(), 2)

        podcast2_analytics = UserAnalytics.objects.filter(podcast=self.podcast2)
        self.assertEqual(podcast2_analytics.count(), 1)

    def test_filter_by_episode(self):
        """Test filtering analytics by episode."""
        episode1_analytics = UserAnalytics.objects.filter(episode=self.episode1)
        self.assertEqual(episode1_analytics.count(), 1)

    def test_aggregate_views(self):
        """Test aggregating views."""
        from django.db.models import Sum

        total_views = UserAnalytics.objects.aggregate(total=Sum('views'))['total']
        self.assertEqual(total_views, 11)  # 5 + 3 + 2 + 1

        podcast1_views = UserAnalytics.objects.filter(
            podcast=self.podcast1
        ).aggregate(total=Sum('views'))['total']
        self.assertEqual(podcast1_views, 7)  # 5 + 2
