"""
Celery tasks for sending emails.

This module contains async tasks for email operations to prevent
blocking the main application flow.
"""

import logging

from celery import shared_task
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.mail import EmailMultiAlternatives
from django.core.validators import validate_email
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


@shared_task
def send_claim_verification_email(verification_id):
    """
    Celery task to email a claim verification link to the podcast's owner.

    The link goes to the RSS-declared ``podcast.owner_email``, never to the
    claimant's own address, so clicking it proves the claimant controls (or is
    vouched for by) the feed owner's inbox. Staff still approve the claim in
    the Django admin afterwards.

    If the podcast has no owner_email, no email is sent and the claim goes
    straight to staff review.

    Args:
        verification_id (int): The ID of the ClaimVerification record

    Returns:
        dict: Dictionary containing success status and details
            - success (bool): Whether the email was sent successfully
            - error (str): Error message (on failure)
    """
    logger.info(
        f"Sending verification email for ClaimVerification ID: {verification_id}"
    )

    try:
        from ..models import ClaimVerification

        # Fetch the verification record
        verification = ClaimVerification.objects.select_related(
            "claim__user", "claim__podcast"
        ).get(pk=verification_id)

        claim = verification.claim
        user = claim.user
        podcast = claim.podcast
        recipient = (podcast.owner_email or "").strip()
        try:
            validate_email(recipient)
        except ValidationError:
            # Empty or malformed (owner_email comes from an untrusted feed).
            recipient = ""

        if not recipient:
            logger.info(
                f"Podcast ID={podcast.id} has no usable owner_email; claim ID={claim.id} "
                "goes to staff review without an email"
            )
            claim.mark_in_review()
            return {
                "success": False,
                "error": "Podcast has no owner_email; sent to staff review",
                "verification_id": verification_id,
            }

        # Generate verification URL
        verification_url = verification.get_verification_url()

        # Prepare email context (addressed to the podcast owner)
        context = {
            # Username only: full names are free text the claimant controls.
            "claimant_name": user.username,
            "podcast_name": podcast.name,
            "verification_url": verification_url,
            "expiry_hours": getattr(settings, "VERIFICATION_EXPIRY_HOURS", 48),
        }

        # Render email templates
        html_content = render_to_string("emails/claim_verification.html", context)
        text_content = render_to_string("emails/claim_verification.txt", context)

        # Prepare subject
        subject = f"Confirm an ownership claim for your podcast - {podcast.name}"

        # Create email message
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[recipient],
        )
        email.attach_alternative(html_content, "text/html")

        # Send email
        email.send(fail_silently=False)

        logger.info(
            f"Verification email sent to the owner_email of podcast ID={podcast.id} "
            f"(verification_id={verification_id})"
        )
        claim.mark_in_review()
        return {
            "success": True,
            "podcast_name": podcast.name,
            "verification_id": verification_id,
        }

    except ClaimVerification.DoesNotExist:
        error_msg = f"ClaimVerification with ID {verification_id} not found"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

    except Exception as e:
        # Never log str(e) or a traceback here: SMTP and address-parsing errors
        # include the recipient address, which comes from an untrusted feed.
        error_msg = f"Error sending verification email: {type(e).__name__}"
        logger.error(f"{error_msg} (verification_id={verification_id})")
        return {"success": False, "error": error_msg}
