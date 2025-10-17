"""
ViewSets for claim verification endpoints.

This module provides API endpoints for verifying podcast ownership claims
through verification tokens sent via email.
"""
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.shortcuts import get_object_or_404
import logging

from audio_processing.models import ClaimVerification
from audio_processing.serializers import (
    ClaimVerificationStatusSerializer,
    ClaimVerificationSuccessSerializer,
    ClaimVerificationErrorSerializer,
)

logger = logging.getLogger(__name__)


class ClaimVerificationView(APIView):
    """
    API view for verifying podcast ownership claims via verification token.

    This endpoint accepts a verification key (UUID) from an email link and
    marks the claim as verified if the token is valid and not expired.
    """

    permission_classes = [AllowAny]  # No authentication required for verification

    def post(self, request, verification_key):
        """
        Verify a podcast claim using the verification key.

        Args:
            request: The HTTP request
            verification_key (str): UUID verification key from the email link

        Returns:
            Response: JSON response with verification status
                - 200: Verification successful
                - 400: Token expired or already verified
                - 404: Verification key not found
        """
        logger.info(f"Received verification request for key: {verification_key}")

        # Fetch the verification record
        verification = get_object_or_404(
            ClaimVerification.objects.select_related('claim__user', 'claim__podcast'),
            verification_key=verification_key
        )

        # Check if already verified
        if verification.is_verified:
            logger.warning(
                f"Verification already completed for key: {verification_key}"
            )
            serializer = ClaimVerificationErrorSerializer(data={
                "success": False,
                "error": "This verification has already been completed.",
                "message": "Your claim has already been verified.",
            })
            serializer.is_valid(raise_exception=True)
            return Response(
                serializer.validated_data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Check if expired
        if verification.is_expired():
            logger.warning(
                f"Verification token expired for key: {verification_key}"
            )
            serializer = ClaimVerificationErrorSerializer(data={
                "success": False,
                "error": "This verification link has expired.",
                "message": "Please request a new verification link.",
            })
            serializer.is_valid(raise_exception=True)
            return Response(
                serializer.validated_data,
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Perform verification
        success = verification.verify()

        if success:
            logger.info(
                f"Claim verification successful: "
                f"ClaimVerification ID={verification.id}, "
                f"Claim ID={verification.claim.id}, "
                f"User={verification.claim.user.email}, "
                f"Podcast={verification.claim.podcast.name}"
            )

            serializer = ClaimVerificationSuccessSerializer(data={
                "success": True,
                "message": "Your podcast ownership claim has been verified successfully!",
                "claim_status": verification.claim.status,
                "podcast_name": verification.claim.podcast.name,
            })
            serializer.is_valid(raise_exception=True)
            return Response(
                serializer.validated_data,
                status=status.HTTP_200_OK,
            )
        else:
            logger.error(
                f"Verification failed for key: {verification_key}"
            )
            serializer = ClaimVerificationErrorSerializer(data={
                "success": False,
                "error": "Verification failed.",
                "message": "An error occurred while verifying your claim.",
            })
            serializer.is_valid(raise_exception=True)
            return Response(
                serializer.validated_data,
                status=status.HTTP_400_BAD_REQUEST,
            )

    def get(self, request, verification_key):
        """
        GET endpoint to check verification status (for frontend to display info).

        Args:
            request: The HTTP request
            verification_key (str): UUID verification key

        Returns:
            Response: JSON response with verification details
        """
        logger.info(f"Checking verification status for key: {verification_key}")

        verification = get_object_or_404(
            ClaimVerification.objects.select_related('claim__user', 'claim__podcast'),
            verification_key=verification_key
        )

        serializer = ClaimVerificationStatusSerializer(data={
            "is_verified": verification.is_verified,
            "is_expired": verification.is_expired(),
            "podcast_name": verification.claim.podcast.name,
            "user_email": verification.claim.user.email,
            "created_at": verification.created_at,
        })
        serializer.is_valid(raise_exception=True)
        return Response(
            serializer.validated_data,
            status=status.HTTP_200_OK,
        )
