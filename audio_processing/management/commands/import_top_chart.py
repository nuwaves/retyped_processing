"""Add the shows on Apple's podcast chart without processing their episodes.

Usage:
    python manage.py import_top_chart [--country us] [--limit 100]

Each new show's feed is imported by a Celery worker, so one must be running.
"""

from django.core.management.base import BaseCommand

from audio_processing.chart_import import import_top_chart


class Command(BaseCommand):
    help = "Add shows from Apple's top podcast chart and import all their episodes, unprocessed"

    def add_arguments(self, parser):
        parser.add_argument(
            "--country", default="us", help="Apple storefront country code"
        )
        parser.add_argument(
            "--limit", type=int, default=100, help="Chart size (max 200)"
        )

    def handle(self, *args, **options):
        summary = import_top_chart(country=options["country"], limit=options["limit"])
        for name in summary["created"]:
            self.stdout.write(f"  added: {name}")
        for name in summary["no_public_feed"]:
            self.stdout.write(f"  no public feed: {name}")
        self.stdout.write(
            self.style.SUCCESS(
                f"{len(summary['created'])} shows added and queued for import, "
                f"{summary['already_present']} already present, "
                f"{len(summary['no_public_feed'])} without a public feed"
            )
        )
