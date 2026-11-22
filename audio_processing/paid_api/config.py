"""
Configuration for the paid transcript API, read from Django settings
(which read the environment; see settings/base.py, "Paid transcript API").
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.conf import settings

# CAIP-2 ids of test networks. Anything else counts as mainnet and needs
# PAID_API_ALLOW_MAINNET=True.
TESTNET_NETWORKS = frozenset(
    {
        "eip155:84532",  # Base Sepolia
    }
)

# The "exact" scheme on EVM networks is the only one implemented.
SUPPORTED_SCHEME = "exact"

EVM_ADDRESS_RE = re.compile(r"^0x[0-9a-fA-F]{40}$")

ADAPTERS = ("x402", "cloudflare")


class PaidApiConfigError(Exception):
    """The paid API is enabled but misconfigured. Fails closed (503)."""


@dataclass(frozen=True)
class Price:
    usd: Decimal
    atomic: str  # amount in the asset's smallest unit, as x402 expects


@dataclass(frozen=True)
class PaidApiConfig:
    adapter: str
    network: str
    asset: str
    asset_name: str
    asset_version: str
    asset_decimals: int
    pay_to: str
    facilitator_url: str
    facilitator_timeout: float
    max_timeout_seconds: int
    price_fetch: Price
    price_search: Price
    rate_limit_per_minute: int
    payer_rate_limit_per_minute: int
    client_ip_header: str
    search_max_limit: int


def _price(value, decimals, name):
    try:
        usd = Decimal(str(value))
    except InvalidOperation as exc:
        raise PaidApiConfigError(f"{name} is not a number") from exc
    if not usd.is_finite() or usd <= 0:
        raise PaidApiConfigError(f"{name} must be greater than 0")
    atomic = usd * (Decimal(10) ** decimals)
    if atomic != atomic.to_integral_value():
        raise PaidApiConfigError(
            f"{name} has more decimal places than the asset supports ({decimals})"
        )
    return Price(usd=usd, atomic=str(int(atomic)))


def is_enabled():
    """
    True only when the feature flag is on AND the transcript-rights gate has
    been explicitly cleared. Both default to False.
    """
    return bool(
        getattr(settings, "PAID_API_ENABLED", False)
        and getattr(settings, "PAID_API_RIGHTS_CLEARED", False)
    )


def get_config():
    """Build and validate the config. Raises PaidApiConfigError."""
    s = settings
    adapter = getattr(s, "PAID_API_ADAPTER", "x402")
    if adapter not in ADAPTERS:
        raise PaidApiConfigError(f"PAID_API_ADAPTER must be one of {ADAPTERS}")

    network = getattr(s, "PAID_API_NETWORK", "eip155:84532")
    if not network.startswith("eip155:"):
        raise PaidApiConfigError("only EVM (eip155:*) networks are supported")
    if network not in TESTNET_NETWORKS and not getattr(
        s, "PAID_API_ALLOW_MAINNET", False
    ):
        raise PaidApiConfigError(
            f"{network} is not a known testnet; set PAID_API_ALLOW_MAINNET=True "
            "only after the owner approves real payments"
        )

    pay_to = getattr(s, "PAID_API_PAY_TO", "")
    if not EVM_ADDRESS_RE.match(pay_to or ""):
        raise PaidApiConfigError("PAID_API_PAY_TO must be a 0x-prefixed EVM address")

    asset = getattr(s, "PAID_API_ASSET", "")
    if not EVM_ADDRESS_RE.match(asset or ""):
        raise PaidApiConfigError("PAID_API_ASSET must be a 0x-prefixed token address")

    decimals = int(getattr(s, "PAID_API_ASSET_DECIMALS", 6))
    if not 0 <= decimals <= 18:
        raise PaidApiConfigError("PAID_API_ASSET_DECIMALS must be 0-18")

    facilitator_url = (getattr(s, "PAID_API_FACILITATOR_URL", "") or "").rstrip("/")
    if adapter == "x402" and not facilitator_url.startswith("https://"):
        raise PaidApiConfigError("PAID_API_FACILITATOR_URL must be an https URL")

    return PaidApiConfig(
        adapter=adapter,
        network=network,
        asset=asset,
        asset_name=getattr(s, "PAID_API_ASSET_NAME", "USDC"),
        asset_version=str(getattr(s, "PAID_API_ASSET_VERSION", "2")),
        asset_decimals=decimals,
        pay_to=pay_to,
        facilitator_url=facilitator_url,
        facilitator_timeout=float(getattr(s, "PAID_API_FACILITATOR_TIMEOUT", 15)),
        max_timeout_seconds=int(getattr(s, "PAID_API_MAX_TIMEOUT_SECONDS", 60)),
        price_fetch=_price(
            getattr(s, "PAID_API_PRICE_FETCH_USD", "0.01"),
            decimals,
            "PAID_API_PRICE_FETCH_USD",
        ),
        price_search=_price(
            getattr(s, "PAID_API_PRICE_SEARCH_USD", "0.001"),
            decimals,
            "PAID_API_PRICE_SEARCH_USD",
        ),
        rate_limit_per_minute=max(1, int(getattr(s, "PAID_API_RATE_LIMIT", 60))),
        payer_rate_limit_per_minute=max(
            1, int(getattr(s, "PAID_API_PAYER_RATE_LIMIT", 120))
        ),
        client_ip_header=getattr(s, "PAID_API_CLIENT_IP_HEADER", "") or "",
        search_max_limit=max(1, int(getattr(s, "PAID_API_SEARCH_MAX_LIMIT", 20))),
    )
