import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

from ..models import ClaimVerification, PodcastClaim, PodcastOwner

logger = logging.getLogger(__name__)


@receiver(post_save, sender=PodcastClaim)
def create_claim_verification(sender, instance, created, **kwargs):
    """
    Signal handler that creates a ClaimVerification record when a PodcastClaim is created.

    This handler only creates a ClaimVerification if ALL of the following criteria are met:
    1. There is NOT a PodcastOwner with the user's email
    2. The podcast's owner_email is different from the user's email (or is None/empty)
    3. There is NOT already a ClaimVerification for this claim

    Args:
        sender: The model class (PodcastClaim)
        instance: The actual PodcastClaim instance being saved
        created: Boolean indicating if this is a new record
        **kwargs: Additional keyword arguments
    """
    # Only process newly created claims, not updates
    if not created:
        return

    user = instance.user
    podcast = instance.podcast

    # Log the claim creation
    logger.info(
        f"New PodcastClaim created: User={user.email} claiming Podcast={podcast.name} (ID={podcast.id})"
    )

    # Criterion 1: Check if there is NO PodcastOwner with the user's email
    podcast_owner_exists = PodcastOwner.objects.filter(email=user.email).exists()
    if podcast_owner_exists:
        logger.info(
            f"Skipping ClaimVerification creation: PodcastOwner already exists with email={user.email}"
        )
        return

    # Criterion 2: Check if podcast.owner_email is different from user.email
    # (or owner_email is None/empty)
    if podcast.owner_email and podcast.owner_email.lower() == user.email.lower():
        logger.info(
            f"Skipping ClaimVerification creation: Podcast owner_email matches user email={user.email}"
        )
        return

    # Criterion 3: Check if there is NOT already a ClaimVerification for this claim
    verification_exists = ClaimVerification.objects.filter(claim=instance).exists()
    if verification_exists:
        logger.info(
            f"Skipping ClaimVerification creation: ClaimVerification already exists for claim ID={instance.id}"
        )
        return

    # All criteria met - create the ClaimVerification
    try:
        verification = ClaimVerification.objects.create(claim=instance)
        logger.info(
            f"Created ClaimVerification: ID={verification.id}, "
            f"verification_key={verification.verification_key}, "
            f"for PodcastClaim ID={instance.id}"
        )

        # Trigger async email task
        from audio_processing.tasks.email_tasks import send_claim_verification_email

        send_claim_verification_email.delay(verification.id)
        logger.info(
            f"Queued verification email task for ClaimVerification ID={verification.id}, "
            f"user={user.email}"
        )

    except Exception as e:
        logger.error(
            f"Failed to create ClaimVerification for PodcastClaim ID={instance.id}: {str(e)}"
        )
