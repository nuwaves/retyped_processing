"""
Celery tasks for sending emails.

This module contains async tasks for email operations to prevent
blocking the main application flow.
"""
import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger(__name__)


@shared_task
def send_claim_verification_email(verification_id):
    """
    Celery task to send a claim verification email to a user.

    This task is triggered when a ClaimVerification is created and sends
    an email containing a verification link with an encoded token.

    Args:
        verification_id (int): The ID of the ClaimVerification record

    Returns:
        dict: Dictionary containing success status and details
            - success (bool): Whether the email was sent successfully
            - email (str): Recipient email address (on success)
            - error (str): Error message (on failure)
    """
    logger.info(f"Sending verification email for ClaimVerification ID: {verification_id}")

    try:
        from ..models import ClaimVerification, PodcastClaim

        # Fetch the verification record
        verification = ClaimVerification.objects.select_related(
            'claim__user',
            'claim__podcast'
        ).get(pk=verification_id)

        user = verification.claim.user
        podcast = verification.claim.podcast

        # Generate verification URL
        verification_url = verification.get_verification_url()

        # Prepare email context
        context = {
            'user_name': user.get_full_name() or user.username,
            'user_first_name': user.first_name or user.username,
            'podcast_name': podcast.name,
            'verification_url': verification_url,
            'expiry_hours': getattr(settings, 'VERIFICATION_EXPIRY_HOURS', 48),
        }

        # Render email templates
        html_content = render_to_string('emails/claim_verification.html', context)
        text_content = render_to_string('emails/claim_verification.txt', context)

        # Prepare subject
        subject = f"Verify Your Podcast Ownership Claim - {podcast.name}"

        # Create email message
        email = EmailMultiAlternatives(
            subject=subject,
            body=text_content,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[user.email],
        )
        email.attach_alternative(html_content, "text/html")

        # Send email
        email.send(fail_silently=False)

        logger.info(
            f"Verification email sent successfully to {user.email} "
            f"for podcast '{podcast.name}' (verification_id={verification_id})"
        )
        verification.claim.status = PodcastClaim.ClaimStatus.IN_REVIEW
        verification.claim.save()
        return {
            "success": True,
            "email": user.email,
            "podcast_name": podcast.name,
            "verification_id": verification_id,
        }

    except ClaimVerification.DoesNotExist:
        error_msg = f"ClaimVerification with ID {verification_id} not found"
        logger.error(error_msg)
        return {"success": False, "error": error_msg}

    except Exception as e:
        error_msg = f"Error sending verification email: {str(e)}"
        logger.error(f"{error_msg} (verification_id={verification_id})", exc_info=True)
        return {"success": False, "error": error_msg}
