import boto3
from django.conf import settings


def get_s3_client():
    """
    Return a client for the audio bucket. Set AWS_S3_ENDPOINT_URL to use an
    S3-compatible store such as Cloudflare R2 instead of AWS S3.
    """
    endpoint_url = getattr(settings, "AWS_S3_ENDPOINT_URL", None)
    return boto3.client(
        "s3",
        # R2 requires the region "auto"; AWS needs the bucket's real region.
        region_name="auto"
        if endpoint_url
        else getattr(settings, "AWS_REGION", "us-east-1"),
        endpoint_url=endpoint_url,
        aws_access_key_id=getattr(settings, "AWS_ACCESS_KEY_ID", None),
        aws_secret_access_key=getattr(settings, "AWS_SECRET_ACCESS_KEY", None),
    )


def public_audio_url(key):
    """Return the public URL for an object in the audio bucket."""
    return f"{settings.AUDIO_CDN_URL}/{key}"
