import uuid
from django.db import models
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
