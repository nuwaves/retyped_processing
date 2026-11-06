"""Replace our speech-to-text transcripts with the publisher's own.

New episodes pick up publisher transcripts automatically (transcript_manager).
This command handles episodes transcribed before that: it re-reads each feed's
transcript links, and for every episode with a Whisper transcript and a usable
publisher transcript it saves the publisher's version. When the new transcript
marks speakers, the speaker script is redone by naming them (one short LLM
request); otherwise the old script is kept. Each swapped episode is re-indexed
to search. Summaries, quotes and entities are left alone.

Usage:
    python manage.py swap_publisher_transcripts --dry-run
    python manage.py swap_publisher_transcripts --podcast tbpn --limit 50
    python manage.py swap_publisher_transcripts

--dry-run still records the feeds' transcript links on episodes, and downloads
transcripts to report what would happen, but changes no transcripts or scripts.
Episodes whose links turn out unusable are marked so a rerun skips them.
--reparse also redoes episodes that already have a publisher transcript, after
a fix to how transcripts are parsed.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from audio_processing.models import Episode, Podcast
from audio_processing.transcript_manager import (
    apply_publisher_transcript,
    best_publisher_transcript,
)


class Command(BaseCommand):
    help = "Replace Whisper transcripts with publisher transcripts where available"

    def add_arguments(self, parser):
        parser.add_argument(
            "--podcast", action="append", default=[], help="Podcast slug (repeatable)"
        )
        parser.add_argument("--limit", type=int, help="Swap at most this many")
        parser.add_argument(
            "--dry-run", action="store_true", help="Report, change no transcripts"
        )
        parser.add_argument(
            "--reparse",
            action="store_true",
            help="Also redo episodes that already have a publisher transcript",
        )

    def handle(self, *args, **options):
        podcasts = Podcast.objects.filter(is_active=True)
        if options["podcast"]:
            podcasts = Podcast.objects.filter(slug__in=options["podcast"])
        for podcast in podcasts:
            changed = podcast.refresh_transcript_links()
            if changed:
                self.stdout.write(f"{podcast.slug}: {changed} episode(s) got links")

        sources = Q(transcript_source="")
        if options["reparse"]:
            sources |= Q(transcript_source__startswith="publisher:")
        episodes = (
            Episode.objects.filter(sources, podcast__in=podcasts)
            .exclude(Q(transcript__isnull=True) | Q(transcript=""))
            .exclude(transcript_links=[])
            .filter(publisher_transcript_checked_at__isnull=True)
            .exclude(processing_status=Episode.ProcessingStatus.RUNNING)
            .select_related("podcast")
            .order_by("-release_date")
        )
        if options["limit"]:
            episodes = episodes[: options["limit"]]
        episodes = list(episodes)
        self.stdout.write(f"{len(episodes)} episode(s) to check")

        counts = {"swapped": 0, "unusable": 0, "named": 0, "script_kept": 0}
        for episode in episodes:
            transcript = best_publisher_transcript(episode)
            if transcript is None:
                counts["unusable"] += 1
                self.stdout.write(f"- {episode.slug}: no usable publisher transcript")
                if not options["dry_run"]:
                    episode.publisher_transcript_checked_at = timezone.now()
                    episode.save(update_fields=["publisher_transcript_checked_at"])
                continue

            self.stdout.write(
                f"- {episode.slug}: {transcript.source}, "
                f"speakers={transcript.has_speakers}, {transcript.words} words "
                f"(was {len(episode.transcript.split())})"
            )
            if options["dry_run"]:
                counts["swapped"] += 1
                continue

            apply_publisher_transcript(episode, transcript)
            counts["swapped"] += 1
            if transcript.has_speakers:
                if episode.generate_speaker_script():
                    counts["named"] += 1
                else:
                    counts["script_kept"] += 1
                    self.stderr.write("  speaker naming failed; kept the old script")
            try:
                episode.index_to_search()
            except Exception as e:
                self.stderr.write(f"  search re-index failed: {e}")

        verb = "would swap" if options["dry_run"] else "swapped"
        self.stdout.write(
            f"Done: {verb} {counts['swapped']}, unusable {counts['unusable']}"
            + (
                ""
                if options["dry_run"]
                else f", scripts renamed {counts['named']}, "
                f"scripts kept after a failure {counts['script_kept']}"
            )
        )
