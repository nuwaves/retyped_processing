"""
Payment adapters. The views only talk to `PaymentAdapter`, so the settlement
backend can change without touching them.

- X402FacilitatorAdapter: self-hosted x402. This server builds the 402
  challenge and calls an x402 facilitator's /verify and /settle endpoints
  (spec section 7). The default config points at a testnet facilitator.
- CloudflareMonetizationGatewayAdapter: placeholder. Cloudflare's
  Monetization Gateway (x402 at the edge) is a closed US-only beta, and its
  origin-side contract isn't public. It fails closed until it is implemented.
"""

import logging
from dataclasses import dataclass, field

import requests

from .config import PaidApiConfigError

logger = logging.getLogger(__name__)


@dataclass
class VerifyResult:
    is_valid: bool
    payer: str = ""
    reason: str = ""


@dataclass
class SettleResult:
    success: bool
    payer: str = ""
    transaction: str = ""
    network: str = ""
    reason: str = ""
    raw: dict = field(default_factory=dict)
    # For failures: True only when the facilitator clearly rejected the
    # payment (nothing was transferred). False means "unknown": the transfer
    # may have gone through, so the payment must not be treated as unused.
    definite: bool = True

    def as_header(self):
        """SettlementResponse body for the PAYMENT-RESPONSE header."""
        out = {
            "success": self.success,
            "transaction": self.transaction,
            "network": self.network,
            "payer": self.payer,
        }
        if not self.success:
            out["errorReason"] = self.reason or "settlement_failed"
        return out


class PaymentAdapter:
    def verify(self, payment_payload, requirements):  # pragma: no cover
        raise NotImplementedError

    def settle(self, payment_payload, requirements):  # pragma: no cover
        raise NotImplementedError


class X402FacilitatorAdapter(PaymentAdapter):
    def __init__(self, config, session=None):
        self.config = config
        self.session = session or requests.Session()

    def _post(self, path, payment_payload, requirements):
        body = {
            "x402Version": 2,
            "paymentPayload": payment_payload,
            "paymentRequirements": requirements,
        }
        resp = self.session.post(
            f"{self.config.facilitator_url}{path}",
            json=body,
            timeout=self.config.facilitator_timeout,
        )
        try:
            data = resp.json()
        except ValueError:
            data = {}
        if not isinstance(data, dict):
            data = {}
        return resp.status_code, data

    def verify(self, payment_payload, requirements):
        try:
            status, data = self._post("/verify", payment_payload, requirements)
        except requests.RequestException as exc:
            logger.warning("x402 verify failed to reach facilitator: %s", exc)
            return VerifyResult(False, reason="facilitator_unavailable")
        if status != 200 or data.get("isValid") is not True:
            return VerifyResult(
                False,
                payer=str(data.get("payer") or ""),
                reason=str(data.get("invalidReason") or f"verify_http_{status}"),
            )
        return VerifyResult(True, payer=str(data.get("payer") or ""))

    def settle(self, payment_payload, requirements):
        try:
            status, data = self._post("/settle", payment_payload, requirements)
        except requests.RequestException as exc:
            # The facilitator may still have broadcast the transfer. Logged so
            # it can be reconciled on chain; the client gets no content.
            logger.error("x402 settle failed to reach facilitator: %s", exc)
            return SettleResult(
                False,
                network=self.config.network,
                reason="facilitator_unavailable",
                definite=False,
            )
        result = SettleResult(
            success=status == 200 and data.get("success") is True,
            payer=str(data.get("payer") or ""),
            transaction=str(data.get("transaction") or ""),
            network=str(data.get("network") or self.config.network),
            reason=str(data.get("errorReason") or ""),
            raw=data,
        )
        if not result.success:
            explicit = bool(result.reason)
            if not explicit:
                result.reason = f"settle_http_{status}"
            # Only an explicit rejection on a non-5xx answer is final.
            result.definite = (
                explicit and status < 500 and result.reason != "settlement_pending"
            )
            if not result.definite:
                logger.error(
                    "x402 settlement outcome unknown (%s); reconcile tx %s on %s",
                    result.reason,
                    result.transaction,
                    result.network,
                )
        return result


class CloudflareMonetizationGatewayAdapter(PaymentAdapter):
    def __init__(self, config):
        raise PaidApiConfigError(
            "The Cloudflare Monetization Gateway adapter is not implemented "
            "(closed beta; origin contract not public). Use PAID_API_ADAPTER=x402."
        )


def get_adapter(config):
    if config.adapter == "x402":
        return X402FacilitatorAdapter(config)
    if config.adapter == "cloudflare":
        return CloudflareMonetizationGatewayAdapter(config)
    raise PaidApiConfigError(f"unknown adapter {config.adapter}")
