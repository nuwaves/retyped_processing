"""
Serializers for claim verification endpoints.
"""

from rest_framework import serializers


class ClaimVerificationStatusSerializer(serializers.Serializer):
    """
    Serializer for checking claim verification status (GET endpoint).
    """

    is_verified = serializers.BooleanField()
    is_expired = serializers.BooleanField()
    podcast_name = serializers.CharField()
    user_email = serializers.EmailField()
    created_at = serializers.DateTimeField()


class ClaimVerificationSuccessSerializer(serializers.Serializer):
    """
    Serializer for successful claim verification response.
    """

    success = serializers.BooleanField(default=True)
    message = serializers.CharField()
    claim_status = serializers.CharField()
    podcast_name = serializers.CharField()


class ClaimVerificationErrorSerializer(serializers.Serializer):
    """
    Serializer for claim verification error responses.
    """

    success = serializers.BooleanField(default=False)
    error = serializers.CharField()
    message = serializers.CharField()
