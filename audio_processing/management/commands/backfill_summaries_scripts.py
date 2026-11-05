"""Regenerate missing summaries and speaker scripts for processed episodes.

The processing workflow carries on when the summary or script step fails, so
an episode can finish "done" with either one empty. This command finds those
episodes and runs only the missing steps again, then re-indexes them to search.

Usage:
    python manage.py backfill_summaries_scripts --since 2026-11-05T00:00 --until 2026-11-05T02:00 --dry-run
    python manage.py backfill_summaries_scripts --since 2026-11-05T00:00 --until 2026-11-05T02:00
    python manage.py backfill_summaries_scripts --slug founders-439-how-eiichiro-oda-works

Times without an offset are read as UTC. The window filters on when processing
completed.
"""

from datetime import timezone as dt_timezone

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q
from django.utils.dateparse import parse_datetime

from audio_processing.models import Episode


def _parse_time(value, name):
    parsed = parse_datetime(value)
    if parsed is None:
        raise CommandError(f"--{name} is not a valid datetime: {value!r}")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt_timezone.utc)
    return parsed


def _blank(field):
    return Q(**{f"{field}__isnull": True}) | Q(**{field: ""})


class Command(BaseCommand):
    help = "Regenerate missing summaries and speaker scripts for processed episodes"

    def add_arguments(self, parser):
        parser.add_argument("--since", help="Processing completed at or after (ISO)")
        parser.add_argument("--until", help="Processing completed before (ISO)")
        parser.add_argument(
            "--slug", action="append", default=[], help="Episode slug (repeatable)"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="List episodes, change nothing"
        )

    def handle(self, *args, **options):
        slugs = options["slug"]
        if not (slugs or options["since"] or options["until"]):
            raise CommandError("Pass --since/--until or at least one --slug")

        episodes = Episode.objects.exclude(_blank("transcript")).filter(
            _blank("summary") | _blank("script_transcript")
        )
        if slugs:
            episodes = episodes.filter(slug__in=slugs)
        if options["since"]:
            episodes = episodes.filter(
                processing_completed_at__gte=_parse_time(options["since"], "since")
            )
        if options["until"]:
            episodes = episodes.filter(
                processing_completed_at__lt=_parse_time(options["until"], "until")
            )
        episodes = list(episodes.order_by("processing_completed_at", "id"))

        self.stdout.write(f"{len(episodes)} episode(s) missing a summary or script")
        failed = 0
        for episode in episodes:
            missing = []
            if not episode.script_transcript:
                missing.append("script")
            if not episode.summary:
                missing.append("summary")
            self.stdout.write(f"- {episode.slug} (id {episode.id}): {', '.join(missing)}")
            if options["dry_run"]:
                continue

            still_missing = []
            if "script" in missing and not episode.generate_speaker_script():
                still_missing.append("script")
            if "summary" in missing and not episode.generate_summary():
                still_missing.append("summary")

            if len(still_missing) < len(missing):
                try:
                    episode.index_to_search()
                except Exception as e:
                    self.stderr.write(f"  search re-index failed: {e}")

            if still_missing:
                failed += 1
                self.stderr.write(f"  still missing: {', '.join(still_missing)}")
            else:
                self.stdout.write("  fixed")

        if failed:
            raise CommandError(f"{failed} episode(s) still missing a summary or script")
