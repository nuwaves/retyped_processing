"""Regenerate speaker scripts that were cut off before the end.

Before scripts were written in parts, long transcripts hit the model's output
limit and the script stopped part way. Those scripts are much shorter than
their transcript. This command rewrites them with the current script step
(in parts, or by naming speakers for publisher transcripts) and re-indexes
each episode to search. A script is only replaced when the new one is
complete, so stopping part way loses nothing; rerunning picks up the rest.

The work is LLM requests that mostly wait, so it runs several episodes at once
in threads rather than on the Celery worker, which handles one task at a time
and is needed for new episodes. Run it in its own container on prod:

    docker compose run -d --name fix-scripts web \
        python manage.py fix_truncated_scripts --workers 8

Usage:
    python manage.py fix_truncated_scripts --dry-run
    python manage.py fix_truncated_scripts --limit 20 --workers 4
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from django.core.management.base import BaseCommand
from django.db import connections
from django.db.models import F
from django.db.models.functions import Length

from audio_processing.models import Episode

logger = logging.getLogger(__name__)

# A complete script runs about 0.95x its transcript (filler words removed);
# cut-off ones were a median 17% for long transcripts.
COMPLETE_RATIO = 0.8
# Short transcripts fit in one request and were never cut off.
MIN_TRANSCRIPT_CHARS = 40000


def truncated_episodes():
    return (
        Episode.objects.exclude(script_transcript__isnull=True)
        .exclude(script_transcript="")
        .annotate(
            transcript_chars=Length("transcript"),
            script_chars=Length("script_transcript"),
        )
        .filter(
            transcript_chars__gt=MIN_TRANSCRIPT_CHARS,
            script_chars__lt=F("transcript_chars") * COMPLETE_RATIO,
        )
        .exclude(processing_status=Episode.ProcessingStatus.RUNNING)
    )


def fix_episode(episode_id):
    """Rewrite one script. Returns (slug, old chars, new chars or None, secs)."""
    started = time.monotonic()
    episode = Episode.objects.select_related("podcast").get(pk=episode_id)
    old = len(episode.script_transcript or "")
    script = episode.generate_speaker_script()
    if script:
        try:
            episode.index_to_search()
        except Exception as e:
            logger.error(f"Search re-index failed for {episode.slug}: {e}")
    return (
        episode.slug,
        len(episode.transcript),
        old,
        len(script) if script else None,
        time.monotonic() - started,
    )


def fix_episode_in_thread(episode_id):
    """fix_episode, closing the thread's own database connection afterwards."""
    try:
        return fix_episode(episode_id)
    finally:
        connections.close_all()


class Command(BaseCommand):
    help = "Regenerate speaker scripts that were cut off before the end"

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, help="Fix at most this many")
        parser.add_argument(
            "--workers", type=int, default=4, help="Episodes to run at once"
        )
        parser.add_argument(
            "--podcast", action="append", default=[], help="Podcast slug (repeatable)"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="List episodes, change nothing"
        )

    def handle(self, *args, **options):
        episodes = truncated_episodes()
        if options["podcast"]:
            episodes = episodes.filter(podcast__slug__in=options["podcast"])
        # Newest first: the episodes people are most likely to open.
        episodes = episodes.order_by("-release_date")
        if options["limit"]:
            episodes = episodes[: options["limit"]]
        rows = list(
            episodes.values_list("id", "slug", "transcript_chars", "script_chars")
        )
        total_chars = sum(r[2] for r in rows)
        self.stdout.write(
            f"{len(rows)} cut-off script(s), {total_chars:,} transcript characters"
        )
        if options["dry_run"]:
            for _, slug, chars, script_chars in rows:
                self.stdout.write(f"- {slug}: script {script_chars:,} of {chars:,}")
            return

        ids = [r[0] for r in rows]
        fixed = failed = 0
        workers = max(1, options["workers"])

        def report(result):
            nonlocal fixed, failed
            slug, chars, old, new, secs = result
            if new is None:
                failed += 1
                self.stderr.write(f"- {slug}: failed after {secs:.0f}s, kept old")
            else:
                fixed += 1
                self.stdout.write(
                    f"- {slug}: {old:,} -> {new:,} of {chars:,} chars "
                    f"in {secs:.0f}s [{fixed + failed}/{len(ids)}]"
                )
            self.stdout.flush()

        if workers == 1:
            for episode_id in ids:
                report(fix_episode(episode_id))
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(fix_episode_in_thread, i) for i in ids]
                for future in as_completed(futures):
                    try:
                        report(future.result())
                    except Exception as e:
                        failed += 1
                        self.stderr.write(f"- error: {e}")

        self.stdout.write(f"Done: fixed {fixed}, failed {failed}")
