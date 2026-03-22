"""Utilities to submit sitemap pages to Google Search Console (Webmasters API).

Usage (recommended from management command):
  python manage.py submit_sitemaps --service-account /path/key.json --site-url https://www.example.com

Notes:
- Requires google-auth and google-auth-httplib2 or google-auth packaged dependencies:
    pip install google-auth google-auth-httplib2 requests
- The service account must be granted access in Search Console for the target site.
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from urllib.parse import quote, urljoin, urlparse

import requests
from google.auth.transport.requests import AuthorizedSession
from google_auth_oauthlib.flow import InstalledAppFlow

logger = logging.getLogger(__name__)

WEBMASTERS_SCOPE = ["https://www.googleapis.com/auth/webmasters"]
WEBMASTERS_BASE = "https://www.googleapis.com/webmasters/v3"


def _fetch_sitemap_index(sitemap_index_url: str, timeout: int = 30) -> list[str]:
    """Fetch sitemap index and return list of <loc> URLs.

    This will return absolute URLs as found in the sitemap. Caller may join
    relative values to the site root.
    """
    resp = requests.get(sitemap_index_url, timeout=timeout)
    resp.raise_for_status()
    root = ET.fromstring(resp.content)
    locs = [
        elem.text.strip()
        for elem in root.findall(".//{*}loc")
        if elem.text and elem.text.strip()
    ]
    return locs


def submit_sitemaps_to_google(
    site_url: str,
    sitemap_index_url: str | None = None,
    sitemap_urls: list[str] | None = None,
    client_secrets_file: str | None = None,
    timeout: int = 30,
) -> dict[str, object]:
    """Submit sitemap URLs to Google Search Console using a service account.

    Args:
        site_url: exact site URL as in Search Console, e.g. 'https://www.example.com'
        sitemap_index_url: optional sitemap index URL; if provided and sitemap_urls
            is not, the index will be fetched and its <loc> entries used.
        sitemap_urls: optional list of sitemap URLs to submit. If provided, sitemap_index_url is ignored.
        service_account_file: path to service account JSON key file. Required.
        timeout: HTTP timeout in seconds.

    Returns:
        dict mapping sitemap_url -> (status_code or 'error', response_text or exception)
    """
    if not client_secrets_file:
        raise ValueError("client_secrets_file is required")

    if not sitemap_urls:
        if not sitemap_index_url:
            sitemap_index_url = site_url.rstrip("/") + "/sitemap.xml"
        logger.info("Fetching sitemap index: %s", sitemap_index_url)
        sitemap_urls = _fetch_sitemap_index(sitemap_index_url, timeout=timeout)
        logger.info("Found %d sitemap entries", len(sitemap_urls))

    # Interactive OAuth flow using a client secrets JSON file.
    # This will open a local browser and run the OAuth flow to obtain credentials.
    flow = InstalledAppFlow.from_client_secrets_file(
        client_secrets_file, scopes=WEBMASTERS_SCOPE
    )
    creds = flow.run_local_server(port=0)
    authed = AuthorizedSession(creds)

    results: dict[str, object] = {}
    site_encoded = quote(site_url, safe="")

    for sitemap in sitemap_urls:
        parsed = urlparse(sitemap)
        if not parsed.scheme:
            # relative path in sitemap index — join to site root
            sitemap = urljoin(site_url, sitemap)
        sitemap = sitemap.replace("http://", "https://")
        feedpath = quote(sitemap, safe="")
        endpoint = f"{WEBMASTERS_BASE}/sites/{site_encoded}/sitemaps/{feedpath}"
        logger.info("Submitting sitemap: %s", sitemap)
        try:
            resp = authed.put(endpoint, timeout=timeout)
            results[sitemap] = (resp.status_code, resp.text)
            if resp.status_code // 100 != 2:
                logger.warning("Non-2xx response for %s: %s", sitemap, resp.status_code)
            else:
                logger.info(
                    "Submitted successfully: %s (status %s)", sitemap, resp.status_code
                )
        except Exception as exc:
            logger.exception("Failed to submit sitemap %s: %s", sitemap, exc)
            results[sitemap] = ("error", str(exc))

    return results


def main():
    """Small CLI for manual runs (not recommended for production scheduling)."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Submit sitemap(s) to Google Search Console using a service account"
    )
    parser.add_argument(
        "--client-secrets",
        required=True,
        help="Path to OAuth client_secrets.json for interactive auth (will open browser)",
    )
    parser.add_argument(
        "--site-url",
        required=True,
        help="Site URL as configured in Search Console, e.g. https://www.example.com",
    )
    parser.add_argument(
        "--sitemap-index",
        help="URL of sitemap index (if omitted, site_url/sitemap.xml is used)",
    )
    parser.add_argument(
        "--sitemap-urls",
        help="Comma-separated list of sitemap URLs to submit (overrides sitemap-index)",
    )
    args = parser.parse_args()

    sitemap_urls = None
    if args.sitemap_urls:
        sitemap_urls = [u.strip() for u in args.sitemap_urls.split(",") if u.strip()]

    res = submit_sitemaps_to_google(
        site_url=args.site_url,
        sitemap_index_url=args.sitemap_index,
        sitemap_urls=sitemap_urls,
        service_account_file=args.service_account,
        client_secrets_file=args.client_secrets,
    )

    for k, v in res.items():
        print(k, "->", v)


if __name__ == "__main__":
    main()
