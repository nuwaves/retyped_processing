import base64
import json
from unittest.mock import MagicMock, patch

import requests
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from ..models import Episode, Podcast
from ..paid_api import x402
from ..paid_api.adapters import (
    CloudflareMonetizationGatewayAdapter,
    SettleResult,
    VerifyResult,
    X402FacilitatorAdapter,
)
from ..paid_api.config import PaidApiConfigError, get_config, is_enabled

PAY_TO = "0x209693Bc6afc0C5328bA36FaF03C514EF312287C"
PAYER = "0x857b06519E91e3A54538791bDbb0E22373e36b66"

ENABLED = {
    "PAID_API_ENABLED": True,
    "PAID_API_RIGHTS_CLEARED": True,
    "PAID_API_PAY_TO": PAY_TO,
    "PAID_API_NETWORK": "eip155:84532",
    "PAID_API_ASSET": "0x036CbD53842c5426634e7929541eC2318f3dCF7e",
    "PAID_API_FACILITATOR_URL": "https://facilitator.test",
    "PAID_API_PRICE_FETCH_USD": "0.01",
    "PAID_API_PRICE_SEARCH_USD": "0.001",
    "PAID_API_RATE_LIMIT": 60,
    "PAID_API_PAYER_RATE_LIMIT": 120,
}


def decode_header(value):
    return json.loads(base64.b64decode(value))


def payment_header(requirements, nonce="0x01"):
    payload = {
        "x402Version": 2,
        "resource": {"url": "http://testserver/x"},
        "accepted": dict(requirements),
        "payload": {
            "signature": "0xsig",
            "authorization": {"from": PAYER, "to": PAY_TO, "nonce": nonce},
        },
    }
    return base64.b64encode(json.dumps(payload).encode()).decode()


class FakeAdapter:
    def __init__(self, valid=True, settle_ok=True, reason=""):
        self.valid, self.settle_ok, self.reason = valid, settle_ok, reason
        self.verify_calls, self.settle_calls = [], []

    def verify(self, payload, requirements):
        self.verify_calls.append((payload, requirements))
        return VerifyResult(self.valid, payer=PAYER, reason=self.reason)

    def settle(self, payload, requirements):
        self.settle_calls.append((payload, requirements))
        return SettleResult(
            self.settle_ok,
            payer=PAYER,
            transaction="0xabc" if self.settle_ok else "",
            network="eip155:84532",
            reason="" if self.settle_ok else "insufficient_funds",
        )


class ConfigTest(SimpleTestCase):
    def test_disabled_by_default(self):
        self.assertFalse(is_enabled())

    @override_settings(PAID_API_ENABLED=True, PAID_API_RIGHTS_CLEARED=False)
    def test_rights_gate_keeps_it_off(self):
        self.assertFalse(is_enabled())

    @override_settings(**ENABLED)
    def test_price_converts_to_atomic_units(self):
        config = get_config()
        self.assertEqual(config.price_fetch.atomic, "10000")
        self.assertEqual(config.price_search.atomic, "1000")

    @override_settings(**{**ENABLED, "PAID_API_PRICE_FETCH_USD": "0.0000001"})
    def test_price_with_too_many_decimals_rejected(self):
        with self.assertRaises(PaidApiConfigError):
            get_config()

    @override_settings(**{**ENABLED, "PAID_API_PRICE_FETCH_USD": "0"})
    def test_zero_price_rejected(self):
        with self.assertRaises(PaidApiConfigError):
            get_config()

    @override_settings(**{**ENABLED, "PAID_API_NETWORK": "eip155:8453"})
    def test_mainnet_needs_explicit_opt_in(self):
        with self.assertRaises(PaidApiConfigError):
            get_config()

    @override_settings(
        **{**ENABLED, "PAID_API_NETWORK": "eip155:8453", "PAID_API_ALLOW_MAINNET": True}
    )
    def test_mainnet_with_opt_in(self):
        self.assertEqual(get_config().network, "eip155:8453")

    @override_settings(**{**ENABLED, "PAID_API_PAY_TO": ""})
    def test_missing_pay_to_rejected(self):
        with self.assertRaises(PaidApiConfigError):
            get_config()

    @override_settings(**{**ENABLED, "PAID_API_FACILITATOR_URL": "http://insecure"})
    def test_facilitator_must_be_https(self):
        with self.assertRaises(PaidApiConfigError):
            get_config()

    @override_settings(**ENABLED)
    def test_cloudflare_adapter_fails_closed(self):
        with self.assertRaises(PaidApiConfigError):
            CloudflareMonetizationGatewayAdapter(get_config())


class X402FormatTest(SimpleTestCase):
    def setUp(self):
        with override_settings(**ENABLED):
            self.config = get_config()
        self.req = x402.build_requirements(self.config, self.config.price_fetch)

    def test_requirements_shape(self):
        self.assertEqual(self.req["scheme"], "exact")
        self.assertEqual(self.req["amount"], "10000")
        self.assertEqual(self.req["payTo"], PAY_TO)

    def test_decode_round_trip(self):
        data = x402.decode_signature(payment_header(self.req))
        self.assertTrue(x402.accepted_matches(data["accepted"], self.req))

    def test_address_case_insensitive(self):
        accepted = dict(self.req, payTo=PAY_TO.lower())
        self.assertTrue(x402.accepted_matches(accepted, self.req))

    def test_mismatches_rejected(self):
        for field, value in [
            ("amount", "1"),
            ("payTo", PAYER),
            ("network", "eip155:8453"),
            ("asset", PAYER),
            ("scheme", "upto"),
        ]:
            with self.subTest(field=field):
                accepted = dict(self.req, **{field: value})
                self.assertFalse(x402.accepted_matches(accepted, self.req))

    def test_bad_headers_rejected(self):
        bad = [
            "",
            "not base64!",
            base64.b64encode(b"[]").decode(),
            base64.b64encode(json.dumps({"x402Version": 1}).encode()).decode(),
            "A" * (x402.MAX_SIGNATURE_HEADER_BYTES + 1),
        ]
        for value in bad:
            with self.subTest(value=value[:20]):
                with self.assertRaises(x402.InvalidPaymentHeader):
                    x402.decode_signature(value)


class FacilitatorAdapterTest(SimpleTestCase):
    def setUp(self):
        with override_settings(**ENABLED):
            self.config = get_config()
        self.session = MagicMock()
        self.adapter = X402FacilitatorAdapter(self.config, session=self.session)

    def _resp(self, status, data):
        resp = MagicMock(status_code=status)
        resp.json.return_value = data
        return resp

    def test_verify_posts_spec_body(self):
        self.session.post.return_value = self._resp(
            200, {"isValid": True, "payer": PAYER}
        )
        result = self.adapter.verify({"p": 1}, {"r": 1})
        self.assertTrue(result.is_valid)
        url = self.session.post.call_args.args[0]
        body = self.session.post.call_args.kwargs["json"]
        self.assertEqual(url, "https://facilitator.test/verify")
        self.assertEqual(body["x402Version"], 2)
        self.assertEqual(body["paymentPayload"], {"p": 1})
        self.assertEqual(body["paymentRequirements"], {"r": 1})

    def test_verify_invalid(self):
        self.session.post.return_value = self._resp(
            200, {"isValid": False, "invalidReason": "insufficient_funds"}
        )
        result = self.adapter.verify({}, {})
        self.assertFalse(result.is_valid)
        self.assertEqual(result.reason, "insufficient_funds")

    def test_verify_network_error_fails_closed(self):
        self.session.post.side_effect = requests.ConnectionError()
        self.assertFalse(self.adapter.verify({}, {}).is_valid)

    def test_settle_success_and_failure(self):
        self.session.post.return_value = self._resp(
            200, {"success": True, "transaction": "0xabc", "payer": PAYER}
        )
        self.assertTrue(self.adapter.settle({}, {}).success)
        self.session.post.return_value = self._resp(500, {"success": True})
        self.assertFalse(self.adapter.settle({}, {}).success)


@override_settings(**ENABLED)
class PaidApiViewTest(TestCase):
    def setUp(self):
        cache.clear()
        self.podcast = Podcast.objects.create(
            name="Paid Test Show", url="https://example.com/paid-feed.xml"
        )
        self.episode = Episode.objects.create(
            title="Rust ownership deep dive",
            podcast=self.podcast,
            transcript="Today we talk about rust ownership and borrowing.",
            has_public_transcript=True,
        )
        self.episode.index_to_search()
        self.private = Episode.objects.create(
            title="Rust private episode",
            podcast=self.podcast,
            transcript="Rust transcript we may not sell.",
            has_public_transcript=False,
        )
        self.private.index_to_search()
        self.url = reverse(
            "v1:api-v1-paid-transcript", kwargs={"slug": self.episode.slug}
        )
        self.adapter = FakeAdapter()
        patcher = patch(
            "audio_processing.paid_api.views.get_adapter", return_value=self.adapter
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _requirements(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 402)
        return decode_header(resp["PAYMENT-REQUIRED"])["accepts"][0]

    def _pay(self, url, requirements, nonce="0x01"):
        return self.client.get(
            url, HTTP_PAYMENT_SIGNATURE=payment_header(requirements, nonce)
        )

    @override_settings(PAID_API_ENABLED=False)
    def test_disabled_returns_404(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("v1:api-v1-paid-info")).status_code, 404
        )

    @override_settings(PAID_API_RIGHTS_CLEARED=False)
    def test_rights_not_cleared_returns_404(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)

    @override_settings(PAID_API_PAY_TO="")
    def test_misconfigured_returns_503(self):
        self.assertEqual(self.client.get(self.url).status_code, 503)

    def test_info_is_free(self):
        resp = self.client.get(reverse("v1:api-v1-paid-info"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["endpoints"]["transcript"]["price_usd"], "0.01")

    def test_unpaid_request_gets_402_challenge(self):
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 402)
        required = decode_header(resp["PAYMENT-REQUIRED"])
        self.assertEqual(required["x402Version"], 2)
        self.assertEqual(required["accepts"][0]["amount"], "10000")
        self.assertEqual(required["accepts"][0]["payTo"], PAY_TO)
        self.assertNotIn("rust ownership", resp.content.decode())

    def test_missing_episode_is_404_before_any_charge(self):
        url = reverse("v1:api-v1-paid-transcript", kwargs={"slug": "nope"})
        resp = self._pay(url, self._requirements())
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(self.adapter.verify_calls, [])

    def test_ineligible_episode_not_sold(self):
        url = reverse("v1:api-v1-paid-transcript", kwargs={"slug": self.private.slug})
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_private_episode_not_in_eligible_set(self):
        from ..paid_api.views import eligible_episodes

        self.assertNotIn(self.private, eligible_episodes())

    def test_paid_request_returns_transcript(self):
        resp = self._pay(self.url, self._requirements())
        self.assertEqual(resp.status_code, 200)
        self.assertIn("rust ownership", resp.json()["transcript"]["text"])
        settlement = decode_header(resp["PAYMENT-RESPONSE"])
        self.assertTrue(settlement["success"])
        self.assertEqual(len(self.adapter.verify_calls), 1)
        self.assertEqual(len(self.adapter.settle_calls), 1)
        self.assertEqual(resp["Cache-Control"], "no-store")

    def test_wrong_amount_rejected_without_facilitator_call(self):
        req = dict(self._requirements(), amount="1")
        resp = self._pay(self.url, req)
        self.assertEqual(resp.status_code, 402)
        self.assertEqual(self.adapter.verify_calls, [])

    def test_search_payment_cannot_buy_a_transcript(self):
        search_url = reverse("v1:api-v1-paid-search") + "?q=rust"
        search_req = decode_header(self.client.get(search_url)["PAYMENT-REQUIRED"])[
            "accepts"
        ][0]
        resp = self._pay(self.url, search_req)
        self.assertEqual(resp.status_code, 402)

    def test_invalid_payment_gets_no_content(self):
        self.adapter.valid = False
        self.adapter.reason = "invalid_signature"
        resp = self._pay(self.url, self._requirements())
        self.assertEqual(resp.status_code, 402)
        self.assertEqual(self.adapter.settle_calls, [])
        self.assertNotIn("rust ownership", resp.content.decode())

    def test_failed_settlement_gets_no_content(self):
        self.adapter.settle_ok = False
        resp = self._pay(self.url, self._requirements())
        self.assertEqual(resp.status_code, 402)
        self.assertNotIn("rust ownership", resp.content.decode())
        self.assertFalse(decode_header(resp["PAYMENT-RESPONSE"])["success"])

    def test_replayed_payment_rejected(self):
        req = self._requirements()
        self.assertEqual(self._pay(self.url, req).status_code, 200)
        resp = self._pay(self.url, req)
        self.assertEqual(resp.status_code, 402)
        self.assertEqual(len(self.adapter.verify_calls), 1)

    @override_settings(PAID_API_RATE_LIMIT=2)
    def test_ip_rate_limit(self):
        self.client.get(self.url)
        self.client.get(self.url)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 429)
        self.assertIn("Retry-After", resp)

    @override_settings(PAID_API_PAYER_RATE_LIMIT=1)
    def test_payer_rate_limit(self):
        req = self._requirements()
        self.assertEqual(self._pay(self.url, req, nonce="0x01").status_code, 200)
        self.assertEqual(self._pay(self.url, req, nonce="0x02").status_code, 429)
        self.assertEqual(len(self.adapter.settle_calls), 1)

    def test_paid_search_returns_only_eligible_episodes(self):
        url = reverse("v1:api-v1-paid-search") + "?q=rust"
        req = decode_header(self.client.get(url)["PAYMENT-REQUIRED"])["accepts"][0]
        self.assertEqual(req["amount"], "1000")
        resp = self._pay(url, req)
        self.assertEqual(resp.status_code, 200)
        slugs = [r["slug"] for r in resp.json()["results"]]
        self.assertEqual(slugs, [self.episode.slug])
        self.assertNotIn("transcript", resp.json()["results"][0])

    def test_search_validates_query_before_charging(self):
        resp = self.client.get(reverse("v1:api-v1-paid-search"))
        self.assertEqual(resp.status_code, 400)
        resp = self.client.get(reverse("v1:api-v1-paid-search") + "?q=" + "a" * 300)
        self.assertEqual(resp.status_code, 400)
