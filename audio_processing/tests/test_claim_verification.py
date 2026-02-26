"""
Tests for claim verification email flow.

This module tests the complete verification workflow including:
- Email task execution
- Verification URL generation
- API endpoint verification
- Token expiration handling
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.sites.models import Site
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from audio_processing.models import (
    ClaimVerification,
    Podcast,
    PodcastClaim,
)
from audio_processing.tasks.email_tasks import send_claim_verification_email


class ClaimVerificationModelTest(TestCase):
    """Test ClaimVerification model methods."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User"
        )
        self.podcast = Podcast.objects.create(
            name="Test Podcast",
            url="https://example.com/podcast/rss",
            owner_email="owner@example.com"
        )
        self.claim = PodcastClaim.objects.create(
            user=self.user,
            podcast=self.podcast
        )
        self.verification = ClaimVerification.objects.create(claim=self.claim)

    def test_get_verification_url(self):
        """Test verification URL generation using Django Sites framework."""
        url = self.verification.get_verification_url()
        self.assertIn(str(self.verification.verification_key), url)
        self.assertIn('/verify-claim/', url)

        # Should use the current site's domain
        current_site = Site.objects.get_current()
        self.assertIn(current_site.domain, url)

    def test_get_verification_url_with_custom_site(self):
        """Test verification URL with custom site domain."""
        # Update the site domain
        site = Site.objects.get_current()
        site.domain = 'example.com'
        site.save()

        url = self.verification.get_verification_url()
        self.assertTrue('example.com' in url)
        self.assertIn(str(self.verification.verification_key), url)

    def test_is_expired_not_expired(self):
        """Test that new verification is not expired."""
        self.assertFalse(self.verification.is_expired())

    @override_settings(VERIFICATION_EXPIRY_HOURS=1)
    def test_is_expired_after_expiry_time(self):
        """Test that verification expires after configured time."""
        # Manually set created_at to past
        past_time = timezone.now() - timedelta(hours=2)
        self.verification.created_at = past_time
        self.verification.save()
        self.assertTrue(self.verification.is_expired())

    def test_verify_success(self):
        """Test successful verification."""
        result = self.verification.verify()
        self.assertTrue(result)
        self.assertTrue(self.verification.is_verified)

        # Check that claim status was updated
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, PodcastClaim.ClaimStatus.APPROVED)

    def test_verify_already_verified(self):
        """Test that verifying again returns False."""
        self.verification.verify()
        result = self.verification.verify()
        self.assertFalse(result)

    @override_settings(VERIFICATION_EXPIRY_HOURS=1)
    def test_verify_expired(self):
        """Test that expired verification cannot be verified."""
        # Set to expired
        past_time = timezone.now() - timedelta(hours=2)
        self.verification.created_at = past_time
        self.verification.save()

        result = self.verification.verify()
        self.assertFalse(result)
        self.assertFalse(self.verification.is_verified)


class EmailTaskTest(TestCase):
    """Test email sending task."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User"
        )
        self.podcast = Podcast.objects.create(
            name="Test Podcast",
            url="https://example.com/podcast/rss",
            owner_email="owner@example.com"
        )
        self.claim = PodcastClaim.objects.create(
            user=self.user,
            podcast=self.podcast
        )
        self.verification = ClaimVerification.objects.create(claim=self.claim)

    def test_send_claim_verification_email_success(self):
        """Test that verification email is sent successfully."""
        result = send_claim_verification_email(self.verification.id)

        self.assertTrue(result['success'])
        self.assertEqual(result['email'], self.user.email)

        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Verify email content
        self.assertIn(self.podcast.name, email.subject)
        self.assertIn(self.user.first_name, email.body)
        self.assertIn(str(self.verification.verification_key), email.body)
        self.assertEqual(email.to, [self.user.email])

    def test_send_claim_verification_email_html_content(self):
        """Test that email contains HTML alternative."""
        send_claim_verification_email(self.verification.id)

        email = mail.outbox[0]
        self.assertTrue(len(email.alternatives) > 0)
        html_content = email.alternatives[0][0]
        self.assertIn(self.podcast.name, html_content)
        self.assertIn('Verify Podcast Ownership', html_content)

    def test_send_claim_verification_email_not_found(self):
        """Test email task with non-existent verification."""
        result = send_claim_verification_email(99999)

        self.assertFalse(result['success'])
        self.assertIn('not found', result['error'])
        self.assertEqual(len(mail.outbox), 0)

    def test_send_claim_verification_email_includes_verification_url(self):
        """Test that email contains the verification URL."""
        send_claim_verification_email(self.verification.id)

        email = mail.outbox[0]
        verification_url = self.verification.get_verification_url()

        # Check both plain text and HTML versions
        self.assertIn(verification_url, email.body)
        html_content = email.alternatives[0][0]
        self.assertIn(verification_url, html_content)


class ClaimVerificationAPITest(TestCase):
    """Test claim verification API endpoint."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="testpass123",
            first_name="Test",
            last_name="User"
        )
        self.podcast = Podcast.objects.create(
            name="Test Podcast",
            url="https://example.com/podcast/rss",
            owner_email="owner@example.com"
        )
        self.claim = PodcastClaim.objects.create(
            user=self.user,
            podcast=self.podcast
        )
        self.verification = ClaimVerification.objects.create(claim=self.claim)

    def test_post_verification_success(self):
        """Test successful claim verification via API."""
        url = f'/api/v1/claims/verify/{self.verification.verification_key}/'
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data['success'])
        self.assertEqual(data['podcast_name'], self.podcast.name)

        # Verify database was updated
        self.verification.refresh_from_db()
        self.assertTrue(self.verification.is_verified)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, PodcastClaim.ClaimStatus.APPROVED)

    def test_post_verification_already_verified(self):
        """Test verifying an already verified claim."""
        # First verification
        self.verification.verify()

        # Try to verify again
        url = f'/api/v1/claims/verify/{self.verification.verification_key}/'
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('already been verified', data['message'])

    @override_settings(VERIFICATION_EXPIRY_HOURS=1)
    def test_post_verification_expired(self):
        """Test verifying an expired token."""
        # Make verification expired
        past_time = timezone.now() - timedelta(hours=2)
        self.verification.created_at = past_time
        self.verification.save()

        url = f'/api/v1/claims/verify/{self.verification.verification_key}/'
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data['success'])
        self.assertIn('expired', data['error'])

    def test_post_verification_invalid_key(self):
        """Test verification with invalid key."""
        invalid_key = uuid.uuid4()
        url = f'/api/v1/claims/verify/{invalid_key}/'
        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)

    def test_verification_endpoint_no_authentication_required(self):
        """Test that verification endpoint doesn't require authentication."""
        url = f'/api/v1/claims/verify/{self.verification.verification_key}/'
        # Client is not authenticated
        response = self.client.post(url)

        # Should succeed without authentication
        self.assertEqual(response.status_code, 200)


class SignalIntegrationTest(TestCase):
    """Test signal integration with email task."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser",
            email="testuser@example.com",
            password="testpass123"
        )
        self.podcast = Podcast.objects.create(
            name="Test Podcast",
            url="https://example.com/podcast/rss",
            owner_email="owner@example.com"
        )

    @patch('audio_processing.tasks.email_tasks.send_claim_verification_email')
    def test_signal_triggers_email_task(self, mock_email_task):
        """Test that creating a claim triggers the email task."""
        # Create claim (should trigger signal)
        claim = PodcastClaim.objects.create(
            user=self.user,
            podcast=self.podcast
        )

        # Verify that ClaimVerification was created
        verification = ClaimVerification.objects.get(claim=claim)
        self.assertIsNotNone(verification)

        # Verify that email task was queued
        mock_email_task.delay.assert_called_once_with(verification.id)

    def test_signal_sends_actual_email(self):
        """Test that signal triggers actual email sending (integration test)."""
        # Create claim
        claim = PodcastClaim.objects.create(
            user=self.user,
            podcast=self.podcast
        )

        # Get the created verification
        verification = ClaimVerification.objects.get(claim=claim)

        # Manually run the task (simulating Celery worker)
        send_claim_verification_email(verification.id)

        # Verify email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, [self.user.email])
        self.assertIn(self.podcast.name, email.subject)
