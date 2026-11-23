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
            last_name="User",
        )
        self.podcast = Podcast.objects.create(
            name="Test Podcast",
            url="https://example.com/podcast/rss",
            owner_email="owner@example.com",
        )
        self.claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
        self.verification = ClaimVerification.objects.create(claim=self.claim)

    def test_get_verification_url(self):
        """Test verification URL generation using Django Sites framework."""
        url = self.verification.get_verification_url()
        self.assertIn(str(self.verification.verification_key), url)
        self.assertIn("/verify-claim/", url)

        # Should use the current site's domain
        current_site = Site.objects.get_current()
        self.assertIn(current_site.domain, url)

    def test_get_verification_url_with_custom_site(self):
        """Test verification URL with custom site domain."""
        # Update the site domain
        site = Site.objects.get_current()
        site.domain = "example.com"
        site.save()

        url = self.verification.get_verification_url()
        self.assertTrue("example.com" in url)
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

        # Owner confirmed: claim waits for staff, never APPROVED here
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, PodcastClaim.ClaimStatus.IN_REVIEW)

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
            last_name="User",
        )
        self.podcast = Podcast.objects.create(
            name="Test Podcast",
            url="https://example.com/podcast/rss",
            owner_email="owner@example.com",
        )
        self.claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
        self.verification = ClaimVerification.objects.create(claim=self.claim)

    def test_send_claim_verification_email_success(self):
        """Test that verification email is sent successfully."""
        result = send_claim_verification_email(self.verification.id)

        self.assertTrue(result["success"])
        self.assertNotIn("email", result)

        # Check that email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]

        # Verify email content
        self.assertIn(self.podcast.name, email.subject)
        self.assertIn(self.user.username, email.body)
        self.assertIn(str(self.verification.verification_key), email.body)
        self.assertEqual(email.to, [self.podcast.owner_email])

    def test_send_claim_verification_email_html_content(self):
        """Test that email contains HTML alternative."""
        send_claim_verification_email(self.verification.id)

        email = mail.outbox[0]
        self.assertTrue(len(email.alternatives) > 0)
        html_content = email.alternatives[0][0]
        self.assertIn(self.podcast.name, html_content)
        self.assertIn("Confirm Ownership Claim", html_content)

    def test_send_claim_verification_email_not_found(self):
        """Test email task with non-existent verification."""
        result = send_claim_verification_email(99999)

        self.assertFalse(result["success"])
        self.assertIn("not found", result["error"])
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
            last_name="User",
        )
        self.podcast = Podcast.objects.create(
            name="Test Podcast",
            url="https://example.com/podcast/rss",
            owner_email="owner@example.com",
        )
        self.claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
        self.verification = ClaimVerification.objects.create(claim=self.claim)

    def test_post_verification_success(self):
        """Test successful claim verification via API."""
        url = f"/api/v1/claims/verify/{self.verification.verification_key}/"
        response = self.client.post(url)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["podcast_name"], self.podcast.name)

        # Verify database was updated
        self.verification.refresh_from_db()
        self.assertTrue(self.verification.is_verified)

        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, PodcastClaim.ClaimStatus.IN_REVIEW)

    def test_post_verification_already_verified(self):
        """Test verifying an already verified claim."""
        # First verification
        self.verification.verify()

        # Try to verify again
        url = f"/api/v1/claims/verify/{self.verification.verification_key}/"
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("already been verified", data["message"])

    @override_settings(VERIFICATION_EXPIRY_HOURS=1)
    def test_post_verification_expired(self):
        """Test verifying an expired token."""
        # Make verification expired
        past_time = timezone.now() - timedelta(hours=2)
        self.verification.created_at = past_time
        self.verification.save()

        url = f"/api/v1/claims/verify/{self.verification.verification_key}/"
        response = self.client.post(url)

        self.assertEqual(response.status_code, 400)
        data = response.json()
        self.assertFalse(data["success"])
        self.assertIn("expired", data["error"])

    def test_post_verification_invalid_key(self):
        """Test verification with invalid key."""
        invalid_key = uuid.uuid4()
        url = f"/api/v1/claims/verify/{invalid_key}/"
        response = self.client.post(url)

        self.assertEqual(response.status_code, 404)

    def test_verification_endpoint_no_authentication_required(self):
        """Test that verification endpoint doesn't require authentication."""
        url = f"/api/v1/claims/verify/{self.verification.verification_key}/"
        # Client is not authenticated
        response = self.client.post(url)

        # Should succeed without authentication
        self.assertEqual(response.status_code, 200)


class SignalIntegrationTest(TestCase):
    """Test signal integration with email task."""

    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username="testuser", email="testuser@example.com", password="testpass123"
        )
        self.podcast = Podcast.objects.create(
            name="Test Podcast",
            url="https://example.com/podcast/rss",
            owner_email="owner@example.com",
        )

    @patch("audio_processing.tasks.email_tasks.send_claim_verification_email")
    def test_signal_triggers_email_task(self, mock_email_task):
        """Test that creating a claim triggers the email task."""
        # Create claim (should trigger signal); the task is queued on commit
        with self.captureOnCommitCallbacks(execute=True):
            claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)

        # Verify that ClaimVerification was created
        verification = ClaimVerification.objects.get(claim=claim)
        self.assertIsNotNone(verification)

        # Verify that email task was queued
        mock_email_task.delay.assert_called_once_with(verification.id)

    def test_signal_sends_actual_email(self):
        """Test that signal triggers actual email sending (integration test)."""
        # Create claim
        claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)

        # Get the created verification
        verification = ClaimVerification.objects.get(claim=claim)

        # Manually run the task (simulating Celery worker)
        send_claim_verification_email(verification.id)

        # Verify email was sent
        self.assertEqual(len(mail.outbox), 1)
        email = mail.outbox[0]
        self.assertEqual(email.to, ["owner@example.com"])
        self.assertNotIn(self.user.email, email.to)
        self.assertIn(self.podcast.name, email.subject)


class ClaimOwnerEmailVerificationTest(TestCase):
    """D5: proof goes to the RSS owner_email; only staff approve."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="claimant", email="claimant@example.com", password="pw12345!"
        )
        self.podcast = Podcast.objects.create(
            name="Owned Podcast",
            url="https://example.com/owned/rss",
            owner_email="owner@example.com",
        )

    def _run_task_for(self, claim):
        verification = ClaimVerification.objects.get(claim=claim)
        send_claim_verification_email(verification.id)
        return verification

    def test_claimant_address_never_receives_key(self):
        claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
        verification = self._run_task_for(claim)
        key = str(verification.verification_key)
        self.assertEqual(len(mail.outbox), 1)
        for message in mail.outbox:
            self.assertNotIn(self.user.email, message.to + message.cc + message.bcc)
            self.assertIn(key, message.body)
            self.assertEqual(message.to, ["owner@example.com"])

    def test_full_flow_never_approves_without_staff(self):
        claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
        verification = self._run_task_for(claim)
        claim.refresh_from_db()
        self.assertEqual(claim.status, PodcastClaim.ClaimStatus.IN_REVIEW)

        response = self.client.post(
            f"/api/v1/claims/verify/{verification.verification_key}/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["claim_status"], "IN_REVIEW")
        claim.refresh_from_db()
        self.assertEqual(claim.status, PodcastClaim.ClaimStatus.IN_REVIEW)

    def test_verify_does_not_reopen_rejected_claim(self):
        claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
        verification = ClaimVerification.objects.get(claim=claim)
        PodcastClaim.objects.filter(pk=claim.pk).update(
            status=PodcastClaim.ClaimStatus.REJECTED
        )
        verification.refresh_from_db()
        self.assertTrue(verification.verify())
        claim.refresh_from_db()
        self.assertEqual(claim.status, PodcastClaim.ClaimStatus.REJECTED)

    def test_owner_email_blank_sends_nothing_and_goes_to_staff(self):
        podcast = Podcast.objects.create(
            name="No Owner Email",
            url="https://example.com/noowner/rss",
            owner_email="",
        )
        claim = PodcastClaim.objects.create(user=self.user, podcast=podcast)
        self.assertFalse(ClaimVerification.objects.filter(claim=claim).exists())
        claim.refresh_from_db()
        self.assertEqual(claim.status, PodcastClaim.ClaimStatus.IN_REVIEW)
        self.assertEqual(len(mail.outbox), 0)

    def test_task_with_owner_email_removed_sends_nothing(self):
        claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
        verification = ClaimVerification.objects.get(claim=claim)
        Podcast.objects.filter(pk=self.podcast.pk).update(owner_email=None)
        result = send_claim_verification_email(verification.id)
        self.assertFalse(result["success"])
        self.assertEqual(len(mail.outbox), 0)
        claim.refresh_from_db()
        self.assertEqual(claim.status, PodcastClaim.ClaimStatus.IN_REVIEW)

    def test_invalid_key_does_not_change_claim(self):
        claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
        response = self.client.post(f"/api/v1/claims/verify/{uuid.uuid4()}/")
        self.assertEqual(response.status_code, 404)
        claim.refresh_from_db()
        self.assertEqual(claim.status, PodcastClaim.ClaimStatus.RECEIVED)

    @override_settings(VERIFICATION_EXPIRY_HOURS=1)
    def test_expired_key_does_not_change_claim(self):
        claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
        verification = ClaimVerification.objects.get(claim=claim)
        ClaimVerification.objects.filter(pk=verification.pk).update(
            created_at=timezone.now() - timedelta(hours=2)
        )
        response = self.client.post(
            f"/api/v1/claims/verify/{verification.verification_key}/"
        )
        self.assertEqual(response.status_code, 400)
        claim.refresh_from_db()
        self.assertEqual(claim.status, PodcastClaim.ClaimStatus.RECEIVED)
        verification.refresh_from_db()
        self.assertFalse(verification.is_verified)

    def test_logs_do_not_contain_key_or_email(self):
        with self.assertLogs("audio_processing", level="DEBUG") as logs:
            claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
            verification = self._run_task_for(claim)
            self.client.post(f"/api/v1/claims/verify/{verification.verification_key}/")
        output = "\n".join(logs.output)
        self.assertNotIn(str(verification.verification_key), output)
        self.assertNotIn(self.user.email, output)
        self.assertNotIn("owner@example.com", output)


class PodcastClaimAdminTest(TestCase):
    """Only staff approve claims, through the admin actions."""

    def setUp(self):
        self.staff = User.objects.create_superuser(
            username="staff", email="staff@example.com", password="pw12345!"
        )
        self.user = User.objects.create_user(
            username="claimant", email="claimant@example.com", password="pw12345!"
        )
        self.podcast = Podcast.objects.create(
            name="Admin Podcast",
            url="https://example.com/admin/rss",
            owner_email="owner@example.com",
        )
        self.claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
        self.url = "/admin/audio_processing/podcastclaim/"

    def _action(self, action):
        return self.client.post(
            self.url,
            {"action": action, "_selected_action": [self.claim.pk]},
            follow=True,
        )

    def test_staff_can_approve(self):
        self.client.force_login(self.staff)
        response = self._action("approve_claims")
        self.assertEqual(response.status_code, 200)
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, PodcastClaim.ClaimStatus.APPROVED)

    def test_staff_can_reject(self):
        self.client.force_login(self.staff)
        self._action("reject_claims")
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.status, PodcastClaim.ClaimStatus.REJECTED)

    def test_non_staff_cannot_approve(self):
        self.client.force_login(self.user)
        self._action("approve_claims")
        self.claim.refresh_from_db()
        self.assertNotEqual(self.claim.status, PodcastClaim.ClaimStatus.APPROVED)

    def test_podcast_and_user_are_read_only(self):
        other = Podcast.objects.create(
            name="Other Podcast", url="https://example.com/other/rss"
        )
        self.client.force_login(self.staff)
        self.client.post(
            f"{self.url}{self.claim.pk}/change/",
            {"podcast": other.pk, "user": self.staff.pk},
        )
        self.claim.refresh_from_db()
        self.assertEqual(self.claim.podcast_id, self.podcast.id)
        self.assertEqual(self.claim.user_id, self.user.id)

    def test_changelist_renders(self):
        self.client.force_login(self.staff)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin Podcast")


class ClaimReviewFollowupTest(TestCase):
    """Fixes from the second review of the D5 change."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="claimant2", email="claimant2@example.com", password="pw12345!"
        )
        self.podcast = Podcast.objects.create(
            name="Followup Podcast",
            url="https://example.com/followup/rss",
            owner_email="owner@example.com",
        )

    def test_bad_owner_email_error_does_not_log_addresses(self):
        Podcast.objects.filter(pk=self.podcast.pk).update(
            owner_email="a@x.example, b@y.example"
        )
        self.podcast.refresh_from_db()
        claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
        verification = ClaimVerification.objects.get(claim=claim)
        with self.assertLogs("audio_processing", level="DEBUG") as logs:
            result = send_claim_verification_email(verification.id)
        self.assertFalse(result["success"])
        output = "\n".join(logs.output) + str(result)
        self.assertNotIn("a@x.example", output)
        self.assertNotIn("b@y.example", output)
        self.assertEqual(len(mail.outbox), 0)

    def test_email_uses_username_not_free_text_name(self):
        self.user.first_name = "Retyped Support"
        self.user.last_name = "re-verify at evil.example"
        self.user.save()
        claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
        send_claim_verification_email(ClaimVerification.objects.get(claim=claim).id)
        self.assertNotIn("evil.example", mail.outbox[0].body)
        self.assertIn("claimant2", mail.outbox[0].body)

    def test_staff_rejection_during_send_is_not_undone(self):
        claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
        verification = ClaimVerification.objects.get(claim=claim)
        original_send = mail.EmailMultiAlternatives.send

        def reject_then_send(message, *args, **kwargs):
            PodcastClaim.objects.filter(pk=claim.pk).update(
                status=PodcastClaim.ClaimStatus.REJECTED
            )
            return original_send(message, *args, **kwargs)

        with patch(
            "audio_processing.tasks.email_tasks.EmailMultiAlternatives.send",
            reject_then_send,
        ):
            send_claim_verification_email(verification.id)
        claim.refresh_from_db()
        self.assertEqual(claim.status, PodcastClaim.ClaimStatus.REJECTED)

    def test_verify_on_rejected_claim_does_not_say_under_review(self):
        claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
        verification = ClaimVerification.objects.get(claim=claim)
        PodcastClaim.objects.filter(pk=claim.pk).update(
            status=PodcastClaim.ClaimStatus.REJECTED
        )
        response = self.client.post(
            f"/api/v1/claims/verify/{verification.verification_key}/"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["claim_status"], "REJECTED")
        self.assertNotIn("review", response.json()["message"])

    def test_verification_str_has_no_key(self):
        claim = PodcastClaim.objects.create(user=self.user, podcast=self.podcast)
        verification = ClaimVerification.objects.get(claim=claim)
        self.assertNotIn(str(verification.verification_key), str(verification))

    def test_claim_creation_is_throttled(self):
        from django.core.cache import cache
        from rest_framework.test import APIClient

        cache.clear()
        client = APIClient()
        client.force_authenticate(self.user)
        statuses = []
        for i in range(11):
            podcast = Podcast.objects.create(
                name=f"Throttle {i}",
                url=f"https://example.com/throttle{i}/rss",
                owner_email=None,
            )
            response = client.post("/api/v1/podcast_claims/", {"podcast": podcast.pk})
            statuses.append(response.status_code)
        cache.clear()
        # Throttling runs before validation, so this holds whatever the
        # serializer answers for the first ten requests.
        self.assertNotIn(429, statuses[:10])
        self.assertEqual(statuses[10], 429)
