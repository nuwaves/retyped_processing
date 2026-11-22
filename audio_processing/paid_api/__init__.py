"""
Paid transcript API (decision D18, 2026-11-22): search and fetch transcripts
for a per-request stablecoin payment over the x402 protocol (v2, HTTP transport).

OFF by default. See docs/paid-api.md before turning it on. Nothing in this
package creates wallets or keys: payments go to an address set in the
environment, and verification/settlement is delegated to an x402 facilitator.
"""
