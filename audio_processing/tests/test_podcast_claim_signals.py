"""
Tests for PodcastClaim signal handlers.

These tests verify that ClaimVerification records are automatically
created when PodcastClaims are created under the correct conditions.
"""
from django.test import TestCase
from django.contrib.auth.models import User
from audio_processing.models import (
    Podcast,
    PodcastClaim,
    PodcastOwner,
    ClaimVerification,
)


class PodcastClaimSignalTest(TestCase):
    """
    Test suite for the create_claim_verification signal handler.
    """

    def setUp(self):
        """
        Set up test data that will be used across multiple tests.
        """
        # Create test users
        self.user1 = User.objects.create_user(
            username="testuser1",
            email="testuser1@example.com",
            password="testpass123"
        )
        self.user2 = User.objects.create_user(
            username="testuser2",
            email="testuser2@example.com",
            password="testpass123"
        )
        self.user3 = User.objects.create_user(
            username="testuser3",
            email="testuser3@example.com",
            password="testpass123"
        )

        # Create test podcasts
        self.podcast1 = Podcast.objects.create(
            name="Test Podcast 1",
            url="https://example.com/podcast1/rss",
            owner_email="owner1@example.com"
        )
        self.podcast2 = Podcast.objects.create(
            name="Test Podcast 2",
            url="https://example.com/podcast2/rss",
            owner_email=None  # No owner email set
        )
        self.podcast3 = Podcast.objects.create(
            name="Test Podcast 3",
            url="https://example.com/podcast3/rss",
            owner_email="testuser2@example.com"  # Matches user2's email
        )

    def test_claim_verification_created_when_all_criteria_met(self):
        """
        Test that ClaimVerification is created when all criteria are met:
        - No PodcastOwner with user's email exists
        - Podcast owner_email is different from user's email
        - No ClaimVerification already exists
        """
        # Create a claim
        claim = PodcastClaim.objects.create(
            user=self.user1,
            podcast=self.podcast1
        )

        # Verify that ClaimVerification was created
        self.assertTrue(
            ClaimVerification.objects.filter(claim=claim).exists(),
            "ClaimVerification should be created when all criteria are met"
        )

        verification = ClaimVerification.objects.get(claim=claim)
        self.assertFalse(verification.is_verified)
        self.assertIsNotNone(verification.verification_key)

    def test_claim_verification_created_when_podcast_has_no_owner_email(self):
        """
        Test that ClaimVerification is created when podcast has no owner_email set.
        """
        claim = PodcastClaim.objects.create(
            user=self.user1,
            podcast=self.podcast2
        )

        # Verify that ClaimVerification was created
        self.assertTrue(
            ClaimVerification.objects.filter(claim=claim).exists(),
            "ClaimVerification should be created when podcast has no owner_email"
        )

    def test_claim_verification_not_created_when_podcast_owner_exists(self):
        """
        Test that ClaimVerification is NOT created when a PodcastOwner
        with the user's email already exists.
        """
        # Create a PodcastOwner with user1's email
        PodcastOwner.objects.create(
            podcast=self.podcast1,
            email=self.user1.email,
            first_name="Test",
            last_name="Owner"
        )

        # Create a claim
        claim = PodcastClaim.objects.create(
            user=self.user1,
            podcast=self.podcast1
        )

        # Verify that ClaimVerification was NOT created
        self.assertFalse(
            ClaimVerification.objects.filter(claim=claim).exists(),
            "ClaimVerification should NOT be created when PodcastOwner exists with user's email"
        )

    def test_claim_verification_not_created_when_owner_email_matches(self):
        """
        Test that ClaimVerification is NOT created when the podcast's
        owner_email matches the user's email.
        """
        # Create a claim for podcast3, which has owner_email matching user2's email
        claim = PodcastClaim.objects.create(
            user=self.user2,
            podcast=self.podcast3
        )

        # Verify that ClaimVerification was NOT created
        self.assertFalse(
            ClaimVerification.objects.filter(claim=claim).exists(),
            "ClaimVerification should NOT be created when podcast owner_email matches user email"
        )

    def test_claim_verification_not_created_when_verification_exists(self):
        """
        Test that ClaimVerification is NOT created when one already exists
        for the claim.
        """
        # Create a claim
        claim = PodcastClaim.objects.create(
            user=self.user1,
            podcast=self.podcast1
        )

        # Verify that one ClaimVerification was created
        initial_count = ClaimVerification.objects.filter(claim=claim).count()
        self.assertEqual(initial_count, 1)

        # Try to trigger the signal again by saving the claim
        claim.save()

        # Verify that no additional ClaimVerification was created
        final_count = ClaimVerification.objects.filter(claim=claim).count()
        self.assertEqual(
            final_count,
            1,
            "No additional ClaimVerification should be created on claim update"
        )

    def test_claim_verification_case_insensitive_email_matching(self):
        """
        Test that email matching is case-insensitive when comparing
        podcast owner_email with user email.
        """
        # Create a podcast with uppercase owner email
        podcast = Podcast.objects.create(
            name="Test Podcast Case",
            url="https://example.com/podcast-case/rss",
            owner_email="TESTUSER3@EXAMPLE.COM"  # Uppercase version of user3's email
        )

        # Create a claim with user3 (whose email is lowercase)
        claim = PodcastClaim.objects.create(
            user=self.user3,
            podcast=podcast
        )

        # Verify that ClaimVerification was NOT created (case-insensitive match)
        self.assertFalse(
            ClaimVerification.objects.filter(claim=claim).exists(),
            "ClaimVerification should NOT be created when owner_email matches (case-insensitive)"
        )

    def test_multiple_claims_different_users_same_podcast(self):
        """
        Test that ClaimVerification is created for multiple claims
        by different users on the same podcast.
        """
        # Create claims from different users for the same podcast
        claim1 = PodcastClaim.objects.create(
            user=self.user1,
            podcast=self.podcast1
        )
        claim2 = PodcastClaim.objects.create(
            user=self.user3,
            podcast=self.podcast1
        )

        # Verify that ClaimVerification was created for both claims
        self.assertTrue(
            ClaimVerification.objects.filter(claim=claim1).exists(),
            "ClaimVerification should be created for first user's claim"
        )
        self.assertTrue(
            ClaimVerification.objects.filter(claim=claim2).exists(),
            "ClaimVerification should be created for second user's claim"
        )

        # Verify they have different verification keys
        verification1 = ClaimVerification.objects.get(claim=claim1)
        verification2 = ClaimVerification.objects.get(claim=claim2)
        self.assertNotEqual(
            verification1.verification_key,
            verification2.verification_key,
            "Each ClaimVerification should have a unique verification_key"
        )

    def test_claim_with_different_status(self):
        """
        Test that ClaimVerification is created regardless of the claim's status,
        as long as it's a new claim.
        """
        # Create a claim with IN_REVIEW status
        claim = PodcastClaim.objects.create(
            user=self.user1,
            podcast=self.podcast2,
            status=PodcastClaim.ClaimStatus.IN_REVIEW
        )

        # Verify that ClaimVerification was created
        self.assertTrue(
            ClaimVerification.objects.filter(claim=claim).exists(),
            "ClaimVerification should be created regardless of claim status"
        )
