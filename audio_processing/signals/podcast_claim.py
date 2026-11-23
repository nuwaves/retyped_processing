import logging

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver

from ..models import ClaimVerification, PodcastClaim, PodcastOwner

logger = logging.getLogger(__name__)


@receiver(post_save, sender=PodcastClaim)
def create_claim_verification(sender, instance, created, **kwargs):
    """
    Route a new PodcastClaim to owner verification or straight to staff review.

    Proof of ownership is a link emailed to the podcast's RSS-declared
    ``owner_email`` (never to the claimant's own address). Every path ends with
    staff approving or rejecting the claim in the Django admin.

    - The podcast has no owner_email: no email is possible, so the claim goes
      straight to IN_REVIEW for staff.
    - A PodcastOwner of THIS podcast already has the claimant's email: no
      email, claim goes to IN_REVIEW for staff.
    - A ClaimVerification already exists for the claim: nothing to do.
    - Otherwise: create a ClaimVerification and email the link to owner_email.
      This also applies when owner_email equals the claimant's email: clicking
      the link proves control of that inbox.

    Logs carry ids only, never email addresses or verification keys.
    """
    # Only process newly created claims, not updates
    if not created:
        return

    user = instance.user
    podcast = instance.podcast

    logger.info(f"New PodcastClaim ID={instance.id} for Podcast ID={podcast.id}")

    if not podcast.owner_email:
        logger.info(
            f"PodcastClaim ID={instance.id}: podcast has no owner_email, "
            "sending to staff review without owner verification"
        )
        _send_to_staff_review(instance)
        return

    if user.email and (
        PodcastOwner.objects.filter(podcast=podcast, email__iexact=user.email).exists()
    ):
        logger.info(
            f"PodcastClaim ID={instance.id}: claimant matches this podcast's "
            "PodcastOwner, sending to staff review"
        )
        _send_to_staff_review(instance)
        return

    if ClaimVerification.objects.filter(claim=instance).exists():
        logger.info(
            f"Skipping ClaimVerification creation: one already exists for "
            f"claim ID={instance.id}"
        )
        return

    try:
        verification = ClaimVerification.objects.create(claim=instance)
        logger.info(
            f"Created ClaimVerification ID={verification.id} "
            f"for PodcastClaim ID={instance.id}"
        )

        # Trigger async email task (sends to podcast.owner_email)
        from audio_processing.tasks.email_tasks import send_claim_verification_email

        verification_id = verification.id
        transaction.on_commit(
            lambda: send_claim_verification_email.delay(verification_id)
        )
        logger.info(
            f"Queued verification email task for ClaimVerification ID={verification.id}"
        )

    except Exception as e:
        logger.error(
            f"Failed to create ClaimVerification for PodcastClaim ID={instance.id}: "
            f"{type(e).__name__}"
        )


def _send_to_staff_review(claim):
    """Move a claim to IN_REVIEW without re-triggering this signal."""
    claim.mark_in_review()
