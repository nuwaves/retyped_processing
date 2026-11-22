# Paid transcript API (x402)

> **STOP: do not launch until the transcript-rights question is settled.**
> retyped hasn't yet decided whether it may *sell* access to transcripts of
> podcasts it doesn't own. Publisher-provided public transcripts and
> approved-owner shows are the only episodes this API will serve, but "public"
> doesn't mean "licensed for resale". The API stays off (404) until
> `PAID_API_RIGHTS_CLEARED=True` (and the free-transcript gate below). Only set that after the owner (Billy) has
> settled the rights question in writing.

Decision D18 (2026-11-22): build monetization now, behind a flag, testnet only.

## Endpoints

| Path | Price | What |
|---|---|---|
| `GET /api/v1/paid/` | free | Prices, network, asset, pay-to address |
| `GET /api/v1/paid/search/?q=<words>&limit=<n>` | `PAID_API_PRICE_SEARCH_USD` (default 0.001) | Matching eligible episodes (metadata, no transcript text) |
| `GET /api/v1/paid/episodes/<slug>/transcript/` | `PAID_API_PRICE_FETCH_USD` (default 0.01) | One full transcript |

Every path returns 404 (for any HTTP method) unless `PAID_API_ENABLED`,
`PAID_API_RIGHTS_CLEARED` **and** `PAID_API_FREE_TRANSCRIPTS_CLOSED` are all
true. The third flag exists because the free `GET /api/v1/episodes/<slug>/`
currently returns full transcripts to anyone; set it only after that free path
is restricted (a separate change and decision).

## Protocol

x402 v2 over HTTP ([spec](https://github.com/coinbase/x402/blob/main/specs/x402-specification-v2.md),
[HTTP transport](https://github.com/coinbase/x402/blob/main/specs/transports-v2/http.md)),
`exact` scheme on EVM, "authorization" flow:

1. The client calls without payment and gets `402` plus a `PAYMENT-REQUIRED` header (base64 JSON: amount, asset, `payTo`, network).
2. The client retries with a `PAYMENT-SIGNATURE` header (a signed EIP-3009 USDC authorization).
3. The server checks that `accepted` equals the requirements it offered (every field, including `extra` and `maxTimeoutSeconds`), then calls the facilitator's `/verify`. It builds the response, calls `/settle`, and returns `200` plus a `PAYMENT-RESPONSE` header. Content is only sent after settlement succeeds.

Guards:
- A missing episode or a bad query is rejected **before** any charge.
- Each signed payment can be used once. The lock is keyed on what was signed (network, asset, `authorization.from`, `authorization.nonce`), not the header text, so re-encoding the header doesn't get around it. Settled payments stay locked with no expiry.
- If settlement fails clearly (the facilitator rejects it), the payment is released and the client gets a 402. If the outcome is unknown (timeout, 5xx, `settlement_pending`), the payment stays locked, no content is sent, and an error log line records the payment id, payer and path. **Those need manual reconciliation on chain; there's no automatic re-check yet.**
- A search with no results is free: it is not settled, and the payment stays unused.
- Bad numeric env values don't crash Django. They disable the paid API (503) with a logged config error.
- Rate limits are per client IP (`PAID_API_RATE_LIMIT`/min, including unpaid 402s) and per payer address (`PAID_API_PAYER_RATE_LIMIT`/min).
- A search payment can't buy a transcript, because the amounts differ. Keep the two prices different.
- Responses are `Cache-Control: no-store`, so Cloudflare won't cache paid content.

## Configuration (environment)

| Variable | Default | Notes |
|---|---|---|
| `PAID_API_ENABLED` | `False` | Feature flag |
| `PAID_API_RIGHTS_CLEARED` | `False` | Rights gate (see the top of this doc) |
| `PAID_API_FREE_TRANSCRIPTS_CLOSED` | `False` | Set only after the free episode API stops returning full transcripts |
| `PAID_API_PAY_TO` | empty | **Public** receiving address. Never put a private key anywhere in this app |
| `PAID_API_NETWORK` | `eip155:84532` | Base Sepolia (testnet) |
| `PAID_API_ALLOW_MAINNET` | `False` | Needed for any non-testnet network; real money |
| `PAID_API_ASSET` | Base Sepolia USDC | Token contract |
| `PAID_API_ASSET_NAME` / `_VERSION` / `_DECIMALS` | `USDC` / `2` / `6` | EIP-712 domain and units |
| `PAID_API_FACILITATOR_URL` | `https://x402.org/facilitator` | Public testnet facilitator. Mainnet needs a production facilitator (e.g. Coinbase CDP, which needs an account) |
| `PAID_API_PRICE_FETCH_USD` / `_SEARCH_USD` | `0.01` / `0.001` | Per request |
| `PAID_API_RATE_LIMIT` / `PAID_API_PAYER_RATE_LIMIT` | `60` / `120` | Per minute |
| `PAID_API_SEARCH_MAX_LIMIT` | `20` | Max search results |
| `PAID_API_CLIENT_IP_HEADER` | empty | **Required behind Cloudflare or any proxy**, e.g. `HTTP_CF_CONNECTING_IP`; otherwise every client shares the proxy's IP and one rate-limit bucket. Only safe when the origin is reachable through Cloudflare alone (tunnel or firewall to Cloudflare IPs); otherwise it can be spoofed |
| `PAID_API_ADAPTER` | `x402` | `cloudflare` is a placeholder that fails closed |

Rate limits and the replay lock need a shared, persistent cache (`REDIS_URL`)
in production. With the local-memory cache they only hold per worker process,
and an evicted or flushed cache forgets settled payments (the facilitator's
on-chain nonce check is then the only replay guard). Moving the lock to a DB
table with a unique constraint is a possible hardening step before mainnet.

Browser clients: `PAYMENT-REQUIRED` / `PAYMENT-RESPONSE` aren't in CORS
exposed headers yet; add them if browser-based payers are in scope.

## Adapters

`audio_processing/paid_api/adapters.py` defines `PaymentAdapter` (`verify`,
`settle`). `X402FacilitatorAdapter` is the self-hosted path.
`CloudflareMonetizationGatewayAdapter` is a stub: Cloudflare's Monetization
Gateway is a closed US-only beta, and its origin contract isn't public. If we
get in, implement it there; the views don't change.

## Before launch (owner sign-off needed for each)
1. Transcript rights settled → `PAID_API_RIGHTS_CLEARED=True`.
2. A receiving address chosen by the owner (no wallet is created by this code).
3. A testnet trial on staging with a test client.
4. Real payments: `PAID_API_ALLOW_MAINNET=True`, mainnet USDC asset, production facilitator.
5. The free `GET /api/v1/episodes/<slug>/` stops returning full `transcript` / `script_transcript` (a separate product decision; it affects the site) → `PAID_API_FREE_TRANSCRIPTS_CLOSED=True`.
6. `PAID_API_CLIENT_IP_HEADER` set and the origin locked to Cloudflare; Redis cache in place.
7. A reconciliation routine for "settlement unknown" log lines.
