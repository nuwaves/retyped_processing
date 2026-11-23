import logging

from django.contrib.auth.models import User
from django.db import models

logger = logging.getLogger(__name__)


class PodcastClaim(models.Model):
    class ClaimStatus(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        IN_REVIEW = "IN_REVIEW", "In Review"
        APPROVED = "APPROVED", "Approved"
        REJECTED = "REJECTED", "Rejected"

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="podcast_claim",
        help_text="Owner of the claim",
    )
    status = models.CharField(
        "Claim status", choices=ClaimStatus, default=ClaimStatus.RECEIVED
    )
    podcast = models.ForeignKey(
        "Podcast",
        on_delete=models.CASCADE,
        related_name="podcast_claim",
        help_text="Podcast this user is claiming as own",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Podcast claim"
        verbose_name_plural = "Podcast claims"

    def __str__(self):
        return f"{self.user} - {self.podcast}"

    def mark_in_review(self):
        """
        Move a RECEIVED claim to IN_REVIEW with a conditional update, so a
        staff decision (APPROVED/REJECTED) made in the meantime is never undone.
        """
        from django.utils import timezone

        PodcastClaim.objects.filter(
            pk=self.pk, status=PodcastClaim.ClaimStatus.RECEIVED
        ).update(status=PodcastClaim.ClaimStatus.IN_REVIEW, updated_at=timezone.now())
        self.refresh_from_db(fields=["status", "updated_at"])
