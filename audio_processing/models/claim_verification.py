import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone

from .podcast_claim import PodcastClaim


class ClaimVerification(models.Model):
    is_verified = models.BooleanField("Verified", default=False)
    verification_key = models.UUIDField(
        "Unique verification key", primary_key=False, default=uuid.uuid4, editable=False
    )
    claim = models.ForeignKey(
        PodcastClaim,
        on_delete=models.CASCADE,
        related_name="claim_verification",
        help_text="Podcast this user is claiming as own",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Podcast claim verification"
        verbose_name_plural = "Podcast claim verifications"

    def __str__(self):
        return f"{self.claim} - {self.verification_key}"

    def get_verification_url(self):
        """
        Generate the verification URL containing the encoded verification key.
        Uses Django's sites framework to get the absolute URL.

        Returns:
            str: Full verification URL with the verification key
        """
        from django.contrib.sites.models import Site

        current_site = Site.objects.get_current()
        frontend_url = f"https://{current_site.domain}/verify-claim/{self.verification_key}"
        return frontend_url

    def is_expired(self):
        """
        Check if the verification token has expired.

        Returns:
            bool: True if expired, False otherwise
        """
        expiry_hours = settings.VERIFICATION_EXPIRY_HOURS or 48
        expiry_time = self.created_at + timedelta(hours=expiry_hours)
        return timezone.now() > expiry_time

    def verify(self):
        """
        Mark this verification as verified and update the associated claim status.

        Returns:
            bool: True if verification was successful, False if already verified or expired
        """
        if self.is_verified:
            return False

        if self.is_expired():
            return False

        # Mark verification as complete
        self.is_verified = True
        self.save(update_fields=["is_verified", "updated_at"])

        # Update the claim status to IN_REVIEW
        self.claim.status = PodcastClaim.ClaimStatus.APPROVED
        self.claim.save(update_fields=["status", "updated_at"])

        return True
