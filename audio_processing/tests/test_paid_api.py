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
    "PAID_API_FREE_TRANSCRIPTS_CLOSED": True,
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


def payment_header(requirements, nonce=1, separators=None):
    payload = {
        "x402Version": 2,
        "resource": {"url": "http://testserver/x"},
        "accepted": dict(requirements),
        "payload": {
            "signature": "0xsig",
            "authorization": {
                "from": PAYER,
                "to": PAY_TO,
                "nonce": f"0x{nonce:064x}",
            },
        },
    }
    raw = json.dumps(payload, separators=separators)
    return base64.b64encode(raw.encode()).decode()


class FakeAdapter:
    def __init__(self, valid=True, settle_ok=True, reason=""):
        self.valid, self.settle_ok, self.reason = valid, settle_ok, reason
        self.settle_definite = True
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
            definite=self.settle_definite,
        )


class ConfigTest(SimpleTestCase):
    def test_disabled_by_default(self):
        self.assertFalse(is_enabled())

    @override_settings(PAID_API_ENABLED=True, PAID_API_RIGHTS_CLEARED=False)
    def test_rights_gate_keeps_it_off(self):
        self.assertFalse(is_enabled())

    @override_settings(**{**ENABLED, "PAID_API_FREE_TRANSCRIPTS_CLOSED": False})
    def test_free_transcripts_gate_keeps_it_off(self):
        self.assertFalse(is_enabled())

    def test_bad_values_fail_closed(self):
        for name, value in [
            ("PAID_API_RATE_LIMIT", ""),
            ("PAID_API_PAYER_RATE_LIMIT", "lots"),
            ("PAID_API_SEARCH_MAX_LIMIT", "0"),
            ("PAID_API_MAX_TIMEOUT_SECONDS", "0"),
            ("PAID_API_FACILITATOR_TIMEOUT", "nan"),
            ("PAID_API_FACILITATOR_TIMEOUT", "-1"),
            ("PAID_API_ASSET_DECIMALS", "x"),
            ("PAID_API_PRICE_FETCH_USD", "1e999999"),
            ("PAID_API_PRICE_SEARCH_USD", "abc"),
        ]:
            with self.subTest(name=name, value=value):
                with override_settings(**{**ENABLED, name: value}):
                    with self.assertRaises(PaidApiConfigError):
                        get_config()

    @override_settings(**{**ENABLED, "PAID_API_RATE_LIMIT": "30"})
    def test_numbers_parsed_from_env_strings(self):
        self.assertEqual(get_config().rate_limit_per_minute, 30)

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

    def test_accepted_must_equal_requirements(self):
        for accepted in [
            dict(self.req, extra={**self.req["extra"], "paymentFlow": "upfront"}),
            dict(self.req, extra={"assetTransferMethod": "permit2"}),
            dict(self.req, maxTimeoutSeconds=999999),
            dict(self.req, amount=10000),
            dict(self.req, unknown="x"),
            {k: v for k, v in self.req.items() if k != "extra"},
        ]:
            with self.subTest(accepted=accepted):
                self.assertFalse(x402.accepted_matches(accepted, self.req))

    def test_authorization_parsing(self):
        good = x402.decode_signature(payment_header(self.req, nonce=7))
        self.assertEqual(x402.authorization(good), (PAYER.lower(), f"0x{7:064x}"))
        for auth in [None, "x", {"from": PAYER}, {"from": "me", "nonce": "0x01"}]:
            with self.subTest(auth=auth):
                payment = {"payload": {"authorization": auth}}
                self.assertIsNone(x402.authorization(payment))

    def test_payment_id_ignores_header_encoding(self):
        a = x402.decode_signature(payment_header(self.req))
        b = x402.decode_signature(payment_header(self.req, separators=(",", ":")))
        self.assertEqual(x402.authorization(a), x402.authorization(b))

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

    def test_settle_definite_only_for_explicit_rejection(self):
        cases = [
            (200, {"success": False, "errorReason": "insufficient_funds"}, True),
            (400, {"success": False, "errorReason": "invalid_signature"}, True),
            (200, {"success": False, "errorReason": "settlement_pending"}, False),
            (502, {}, False),
            (200, {"success": False}, False),
        ]
        for status, data, definite in cases:
            with self.subTest(status=status, data=data):
                self.session.post.side_effect = None
                self.session.post.return_value = self._resp(status, data)
                result = self.adapter.settle({}, {})
                self.assertFalse(result.success)
                self.assertEqual(result.definite, definite)

    def test_settle_timeout_is_not_definite(self):
        self.session.post.side_effect = requests.Timeout()
        result = self.adapter.settle({}, {})
        self.assertFalse(result.success)
        self.assertFalse(result.definite)
        self.assertEqual(result.network, "eip155:84532")


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
            raw_audio_url="https://example.com/audio/public.mp3",
            transcript="Today we talk about rust ownership and borrowing.",
            has_public_transcript=True,
        )
        self.episode.index_to_search()
        self.private = Episode.objects.create(
            title="Rust private episode",
            podcast=self.podcast,
            raw_audio_url="https://example.com/audio/private.mp3",
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

    def _pay(self, url, requirements, nonce=1, separators=None):
        return self.client.get(
            url,
            HTTP_PAYMENT_SIGNATURE=payment_header(requirements, nonce, separators),
        )

    @override_settings(PAID_API_ENABLED=False)
    def test_disabled_returns_404(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("v1:api-v1-paid-info")).status_code, 404
        )

    @override_settings(PAID_API_ENABLED=False)
    def test_disabled_hides_routes_for_every_method(self):
        self.assertEqual(self.client.post(self.url).status_code, 404)

    def test_enabled_rejects_non_get(self):
        self.assertEqual(self.client.post(self.url).status_code, 405)

    @override_settings(PAID_API_FREE_TRANSCRIPTS_CLOSED=False)
    def test_free_path_open_returns_404(self):
        self.assertEqual(self.client.get(self.url).status_code, 404)

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

    def test_reencoded_payment_rejected(self):
        req = self._requirements()
        self.assertEqual(self._pay(self.url, req).status_code, 200)
        resp = self._pay(self.url, req, separators=(",", ":"))
        self.assertEqual(resp.status_code, 402)
        self.assertEqual(len(self.adapter.verify_calls), 1)

    def test_unknown_settlement_keeps_payment_locked(self):
        self.adapter.settle_ok = False
        self.adapter.settle_definite = False
        req = self._requirements()
        self.assertEqual(self._pay(self.url, req).status_code, 402)
        self.adapter.settle_ok = True
        resp = self._pay(self.url, req)
        self.assertEqual(resp.status_code, 402)
        self.assertEqual(len(self.adapter.settle_calls), 1)

    def test_definite_settlement_failure_frees_payment(self):
        self.adapter.settle_ok = False
        req = self._requirements()
        self.assertEqual(self._pay(self.url, req).status_code, 402)
        self.adapter.settle_ok = True
        self.assertEqual(self._pay(self.url, req).status_code, 200)
        self.assertEqual(len(self.adapter.settle_calls), 2)

    def test_search_with_no_results_is_not_charged(self):
        url = reverse("v1:api-v1-paid-search") + "?q=zebra"
        req = decode_header(self.client.get(url)["PAYMENT-REQUIRED"])["accepts"][0]
        resp = self._pay(url, req)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["count"], 0)
        self.assertEqual(self.adapter.settle_calls, [])
        self.assertNotIn("PAYMENT-RESPONSE", resp)

    def test_produce_error_releases_payment(self):
        req = self._requirements()
        with patch(
            "audio_processing.paid_api.views._episode_summary",
            side_effect=RuntimeError("db down"),
        ):
            with self.assertRaises(RuntimeError):
                self._pay(self.url, req)
        self.assertEqual(self._pay(self.url, req).status_code, 200)

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
        self.assertEqual(self._pay(self.url, req, nonce=1).status_code, 200)
        self.assertEqual(self._pay(self.url, req, nonce=2).status_code, 429)
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
