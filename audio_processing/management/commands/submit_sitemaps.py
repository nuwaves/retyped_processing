"""Django management command to submit sitemap pages to Google Search Console.

This command uses an interactive OAuth flow driven by a `client_secrets.json` file
and will open a browser to complete authentication. For automation, consider
granting a service account in Search Console and using a separate non-interactive tool.

Usage:
    python manage.py submit_sitemaps --client-secrets /path/client_secrets.json --site-url https://www.example.com

Optional:
    --sitemap-index URL   (defaults to site_url/sitemap.xml)
    --sitemap-urls CSV    (comma-separated list of sitemap URLs to submit)
"""

from django.core.management.base import BaseCommand

from audio_processing.utils.google_sitemaps import submit_sitemaps_to_google


class Command(BaseCommand):
    help = "Submit sitemap pages to Google Search Console via interactive OAuth (client_secrets.json)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--client-secrets",
            required=True,
            help="Path to OAuth client_secrets.json (will open browser)",
        )
        parser.add_argument(
            "--site-url",
            required=True,
            help="Site URL as configured in Search Console (e.g. https://www.example.com)",
        )
        parser.add_argument("--sitemap-index", help="URL to sitemap index (optional)")
        parser.add_argument(
            "--sitemap-urls",
            help="Comma-separated list of sitemap URLs to submit (optional)",
        )

    def handle(self, *args, **options):
        client_secrets = options.get("client_secrets")
        site_url = options.get("site_url")
        sitemap_index = options.get("sitemap_index")
        sitemap_urls = options.get("sitemap_urls")

        sitemap_list: list | None = None
        if sitemap_urls:
            sitemap_list = [s.strip() for s in sitemap_urls.split(",") if s.strip()]

        results = submit_sitemaps_to_google(
            site_url=site_url,
            sitemap_index_url=sitemap_index,
            sitemap_urls=sitemap_list,
            client_secrets_file=client_secrets,
        )

        # Print a short summary
        for sitemap, res in results.items():
            self.stdout.write(f"{sitemap} -> {res}")
