"""
Paid transcript endpoints (x402 v2, "authorization" flow:
verify -> build response -> settle -> respond).

GET /api/v1/paid/                              free: prices and terms
GET /api/v1/paid/search/?q=...&limit=N         paid: transcript search
GET /api/v1/paid/episodes/<slug>/transcript/   paid: one full transcript

All of them return 404 unless PAID_API_ENABLED and PAID_API_RIGHTS_CLEARED
are both True.
"""

import hashlib
import logging

from django.core.cache import cache
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.views.decorators.http import require_GET

from ..models import Episode
from ..views.search_viewsets import build_search_query
from . import x402
from .adapters import get_adapter
from .config import PaidApiConfigError, get_config, is_enabled
from .ratelimit import hit

logger = logging.getLogger(__name__)

MAX_QUERY_LENGTH = 200


def eligible_episodes():
    """
    Episodes whose transcript may be sold: same rule as
    Episode.public_transcript_allowed (publisher-provided public transcript,
    or an approved podcast owner), and a transcript must exist.
    Whether this rule is enough to SELL access is the open rights question
    (see docs/paid-api.md); PAID_API_RIGHTS_CLEARED gates the whole API on it.
    """
    has_text = (Q(script_transcript__isnull=False) & ~Q(script_transcript="")) | (
        Q(transcript__isnull=False) & ~Q(transcript="")
    )
    rights = Q(has_public_transcript=True) | Q(
        podcast__owner__approval_status="approved"
    )
    return Episode.objects.filter(has_text & rights)


def _client_ip(request, config):
    if config.client_ip_header:
        value = request.META.get(config.client_ip_header, "")
        if value:
            return value.split(",")[0].strip()[:64]
    return request.META.get("REMOTE_ADDR", "unknown")


def _json(data, status=200, headers=None):
    resp = JsonResponse(data, status=status)
    resp["Cache-Control"] = "no-store"
    for key, value in (headers or {}).items():
        resp[key] = value
    return resp


def _payment_required(request, description, requirements, error, extra=None):
    body = x402.build_payment_required(
        request.build_absolute_uri(), description, requirements, error
    )
    headers = {x402.HEADER_REQUIRED: x402.encode(body)}
    headers.update(extra or {})
    return _json(body, status=402, headers=headers)


def _setup(request):
    """Common gate: flag, config, IP rate limit. Returns (config, error_response)."""
    if not is_enabled():
        raise Http404()
    try:
        config = get_config()
    except PaidApiConfigError as exc:
        logger.error("paid API misconfigured: %s", exc)
        return None, _json({"error": "paid API unavailable"}, status=503)
    allowed, retry = hit(
        "ip", _client_ip(request, config), config.rate_limit_per_minute
    )
    if not allowed:
        return None, _json(
            {"error": "rate limit exceeded"},
            status=429,
            headers={"Retry-After": str(retry)},
        )
    return config, None


def _charge(request, config, price, description, produce):
    """
    Run the x402 exchange around `produce()`, which returns the JSON body.
    Content is only returned after settlement succeeds.
    """
    requirements = x402.build_requirements(config, price)
    header = request.META.get(x402.META_SIGNATURE, "")
    if not header:
        return _payment_required(
            request,
            description,
            requirements,
            f"{x402.HEADER_SIGNATURE} header is required",
        )

    try:
        payment = x402.decode_signature(header)
    except x402.InvalidPaymentHeader as exc:
        return _payment_required(request, description, requirements, str(exc))

    if not x402.accepted_matches(payment["accepted"], requirements):
        return _payment_required(
            request, description, requirements, "payment does not match requirements"
        )

    try:
        adapter = get_adapter(config)
    except PaidApiConfigError as exc:
        logger.error("paid API adapter unavailable: %s", exc)
        return _json({"error": "paid API unavailable"}, status=503)

    # One use per signed payment, across workers (needs a shared cache).
    lock_key = "paid_api:payment:" + hashlib.sha256(header.encode()).hexdigest()
    if not cache.add(lock_key, "pending", timeout=config.max_timeout_seconds + 300):
        return _payment_required(
            request, description, requirements, "payment already submitted"
        )

    verified = adapter.verify(payment, requirements)
    if not verified.is_valid:
        cache.delete(lock_key)
        return _payment_required(
            request, description, requirements, f"invalid payment: {verified.reason}"
        )

    if verified.payer:
        allowed, retry = hit(
            "payer", verified.payer.lower(), config.payer_rate_limit_per_minute
        )
        if not allowed:
            cache.delete(lock_key)
            return _json(
                {"error": "rate limit exceeded"},
                status=429,
                headers={"Retry-After": str(retry)},
            )

    body = produce()

    settled = adapter.settle(payment, requirements)
    response_header = {x402.HEADER_RESPONSE: x402.encode(settled.as_header())}
    if not settled.success:
        if settled.reason != "settlement_pending":
            cache.delete(lock_key)
        return _payment_required(
            request,
            description,
            requirements,
            f"settlement failed: {settled.reason}",
            extra=response_header,
        )

    cache.set(lock_key, "settled", timeout=config.max_timeout_seconds + 300)
    logger.info(
        "paid API settled %s %s from %s tx %s",
        price.usd,
        request.path,
        settled.payer,
        settled.transaction,
    )
    return _json(body, headers=response_header)


def _episode_summary(episode):
    return {
        "slug": episode.slug,
        "title": episode.title,
        "podcast": {"name": episode.podcast.name, "slug": episode.podcast.slug}
        if episode.podcast
        else None,
        "release_date": episode.release_date.isoformat()
        if episode.release_date
        else None,
        "url": f"https://retyped.xyz{episode.get_absolute_url()}"
        if episode.podcast
        else None,
    }


@require_GET
def info(request):
    config, error = _setup(request)
    if error:
        return error
    return _json(
        {
            "protocol": "x402",
            "x402Version": x402.X402_VERSION,
            "network": config.network,
            "asset": config.asset,
            "payTo": config.pay_to,
            "endpoints": {
                "search": {
                    "path": "/api/v1/paid/search/?q=<query>&limit=<n>",
                    "price_usd": str(config.price_search.usd),
                },
                "transcript": {
                    "path": "/api/v1/paid/episodes/<slug>/transcript/",
                    "price_usd": str(config.price_fetch.usd),
                },
            },
            "rate_limit_per_minute": config.rate_limit_per_minute,
            "terms": "https://retyped.xyz/terms",
        }
    )


@require_GET
def search(request):
    config, error = _setup(request)
    if error:
        return error

    query = request.GET.get("q", "").strip()
    if not query or len(query) > MAX_QUERY_LENGTH:
        return _json(
            {"error": f"q is required (max {MAX_QUERY_LENGTH} characters)"},
            status=400,
        )
    search_query = build_search_query(query)
    if search_query is None:
        return _json({"error": "q has no searchable words"}, status=400)
    try:
        limit = int(request.GET.get("limit", 10))
    except ValueError:
        limit = 10
    limit = max(1, min(limit, config.search_max_limit))

    def produce():
        episodes = (
            eligible_episodes()
            .filter(search_vector=search_query)
            .select_related("podcast")
            .order_by("-release_date", "-id")[:limit]
        )
        results = [_episode_summary(e) for e in episodes]
        return {"query": query, "count": len(results), "results": results}

    return _charge(
        request,
        config,
        config.price_search,
        "retyped transcript search",
        produce,
    )


@require_GET
def transcript(request, slug):
    config, error = _setup(request)
    if error:
        return error

    # Resolve before charging, so nobody pays for a missing transcript.
    episode = eligible_episodes().select_related("podcast").filter(slug=slug).first()
    if episode is None:
        return _json({"error": "transcript not found"}, status=404)

    def produce():
        if episode.script_transcript:
            fmt, text = "speaker_script", episode.script_transcript
        else:
            fmt, text = "raw", episode.transcript
        return {
            "episode": _episode_summary(episode),
            "transcript": {"format": fmt, "text": text},
            "license": "Single-use access for the paying client. "
            "See https://retyped.xyz/terms. No bulk redistribution.",
        }

    return _charge(
        request,
        config,
        config.price_fetch,
        f"retyped transcript: {episode.slug}",
        produce,
    )
