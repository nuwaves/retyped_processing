"""
x402 v2 wire format helpers (HTTP transport).

Spec: https://github.com/coinbase/x402/blob/main/specs/x402-specification-v2.md
and specs/transports-v2/http.md. Headers carry base64-encoded JSON:
PAYMENT-REQUIRED (server -> client, with 402), PAYMENT-SIGNATURE
(client -> server), PAYMENT-RESPONSE (server -> client, settlement result).
"""

import base64
import binascii
import json

X402_VERSION = 2

HEADER_REQUIRED = "PAYMENT-REQUIRED"
HEADER_SIGNATURE = "PAYMENT-SIGNATURE"
HEADER_RESPONSE = "PAYMENT-RESPONSE"

# Django exposes request headers in META with this name.
META_SIGNATURE = "HTTP_PAYMENT_SIGNATURE"

# A real exact-scheme payload is well under 2 KB; refuse anything huge.
MAX_SIGNATURE_HEADER_BYTES = 8192

# PaymentRequirements fields the client must echo back unchanged in `accepted`.
MATCH_FIELDS = ("scheme", "network", "amount", "asset", "payTo")


class InvalidPaymentHeader(ValueError):
    pass


def encode(obj):
    return base64.b64encode(
        json.dumps(obj, separators=(",", ":"), sort_keys=True).encode()
    ).decode()


def decode_signature(value):
    """Decode a PAYMENT-SIGNATURE header into a dict, or raise."""
    if not value or len(value) > MAX_SIGNATURE_HEADER_BYTES:
        raise InvalidPaymentHeader("missing or oversized payment header")
    try:
        data = json.loads(base64.b64decode(value, validate=True))
    except (binascii.Error, ValueError) as exc:
        raise InvalidPaymentHeader("payment header is not base64 JSON") from exc
    if not isinstance(data, dict):
        raise InvalidPaymentHeader("payment header must be a JSON object")
    if data.get("x402Version") != X402_VERSION:
        raise InvalidPaymentHeader("unsupported x402Version")
    if not isinstance(data.get("accepted"), dict) or not isinstance(
        data.get("payload"), dict
    ):
        raise InvalidPaymentHeader("payment header lacks accepted/payload")
    return data


def build_requirements(config, price):
    """One PaymentRequirements entry for the exact scheme on EVM."""
    return {
        "scheme": "exact",
        "network": config.network,
        "amount": price.atomic,
        "asset": config.asset,
        "payTo": config.pay_to,
        "maxTimeoutSeconds": config.max_timeout_seconds,
        "extra": {"name": config.asset_name, "version": config.asset_version},
    }


def build_payment_required(resource_url, description, requirements, error):
    return {
        "x402Version": X402_VERSION,
        "error": error,
        "resource": {
            "url": resource_url,
            "description": description,
            "mimeType": "application/json",
        },
        "accepts": [requirements],
    }


def accepted_matches(accepted, requirements):
    """
    The client's chosen requirements must be exactly ours on the fields that
    decide who gets paid, how much, in what, and where. Addresses compare
    case-insensitively (EIP-55 checksums vary in case).
    """
    for field in MATCH_FIELDS:
        theirs, ours = accepted.get(field), requirements.get(field)
        if not isinstance(theirs, str):
            return False
        if field in ("asset", "payTo"):
            if theirs.lower() != ours.lower():
                return False
        elif theirs != ours:
            return False
    return True
