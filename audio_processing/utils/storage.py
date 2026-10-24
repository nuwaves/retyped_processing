import boto3
from botocore.config import Config
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
        # boto3 presigns us-east-1 URLs with SigV2 by default, which newer
        # buckets reject.
        config=Config(signature_version="s3v4"),
    )


def public_audio_url(key):
    """Return the public URL for an object in the audio bucket."""
    return f"{settings.AUDIO_CDN_URL}/{key}"


# Seven days is the longest SigV4 allows; Groq batch jobs can take a day or more
# to reach a file.
PRESIGNED_URL_EXPIRY = 7 * 24 * 60 * 60


def audio_download_url(url):
    """
    Return a URL that Groq and the worker can fetch. Audio we stored is saved as
    a public CDN URL; swap it for a presigned link to the bucket so downloads
    don't depend on the CDN. Other URLs (e.g. the publisher's feed) pass through.
    """
    prefix = f"{settings.AUDIO_CDN_URL}/"
    if not url or not url.startswith(prefix):
        return url
    return get_s3_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.AWS_S3_BUCKET, "Key": url[len(prefix) :]},
        ExpiresIn=PRESIGNED_URL_EXPIRY,
    )
