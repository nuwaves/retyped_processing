"""
Pick the best transcript source for each episode.

Many feeds publish their own transcript next to the audio (the Podcasting 2.0
<podcast:transcript> tag), often with speaker turns already marked. Those are
free and usually better than our speech-to-text, so the manager:

- reads every transcript link from the raw feed (feedparser keeps only the
  last tag per episode, which for some hosts is an HTML page),
- downloads them best format first (JSON, VTT, SRT, plain text), checks each
  one covers the episode, and prefers one with speaker turns,
- tells the batch runner to wait a while before paying for speech-to-text
  when the podcast usually publishes transcripts but this episode has none yet.
"""

import json
import logging
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import timedelta

import requests
from constance import config
from django.conf import settings
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

PODCAST_NS = "https://podcastindex.org/namespace/1.0"

# Formats we can read, best first. HTML pages are skipped: they carry no
# timing and their markup varies by host.
FORMAT_RANK = {
    "application/json": ("json", 0),
    "text/vtt": ("vtt", 1),
    "application/x-subrip": ("srt", 2),
    "application/srt": ("srt", 2),
    "text/srt": ("srt", 2),
    "text/plain": ("text", 3),
}

# Download at most this many candidate files per episode.
MAX_CANDIDATES = 4
MAX_TRANSCRIPT_BYTES = 20 * 1024 * 1024

# A transcript must cover this share of the episode's duration (by its last
# timestamp), or, without timestamps, have at least this many words a minute.
MIN_COVERAGE = 0.8
MIN_WORDS_PER_MINUTE = 60
MIN_WORDS = 200

# A podcast "publishes transcripts" when at least this share of its recent
# episodes list one.
RECENT_EPISODES = 10
PUBLISHES_SHARE = 0.5

USER_AGENT = "Retyped/1.0 (+https://retyped.xyz)"


@dataclass
class PublisherTranscript:
    text: str
    format: str
    url: str
    has_speakers: bool
    end_seconds: float | None
    words: int

    @property
    def source(self):
        return f"publisher:{self.format}"


# --- Reading the feed -------------------------------------------------------


def extract_transcript_links(feed_xml):
    """
    Map each item's guid and enclosure URL to its transcript links, as
    [{"url", "type"}], from raw feed XML. Returns {} if the XML can't be read.
    """
    if isinstance(feed_xml, bytes):
        if b"<!ENTITY" in feed_xml:
            return {}
    elif "<!ENTITY" in feed_xml:
        return {}
    try:
        root = ET.fromstring(feed_xml)
    except ET.ParseError:
        return {}

    links_by_key = {}
    for item in root.iter("item"):
        links = [
            {"url": tag.get("url"), "type": (tag.get("type") or "").lower()}
            for tag in item.findall(f"{{{PODCAST_NS}}}transcript")
            if tag.get("url")
        ]
        if not links:
            continue
        guid = (item.findtext("guid") or "").strip()
        enclosure = item.find("enclosure")
        for key in (guid, enclosure.get("url") if enclosure is not None else None):
            if key:
                links_by_key[key] = links
    return links_by_key


def links_for_entry(links_by_key, entry, audio_url=None):
    """The transcript links for a feedparser entry, matched by guid or audio URL."""
    if not isinstance(links_by_key, dict):
        return []
    for key in (entry.get("id"), audio_url):
        if key and key in links_by_key:
            return links_by_key[key]
    return []


# --- Parsing transcript files ------------------------------------------------

GENERIC_SPEAKER = re.compile(r"^speaker[\s_-]*(\d+)$", re.IGNORECASE)
CUE_TIME = re.compile(
    r"(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})\s*-->\s*(?:(\d+):)?(\d{1,2}):(\d{2})[.,](\d{1,3})"
)
VOICE = re.compile(r"<v(?:\.[^\s>]*)?\s+([^>]+)>")
TAG = re.compile(r"<[^>]+>")


def _zero_based(names):
    """True when generic labels start at 0, as in "SPEAKER_00"."""
    for name in names:
        match = GENERIC_SPEAKER.match((name or "").strip())
        if match and int(match.group(1)) == 0:
            return True
    return False


def normalize_speaker(name, zero_based=False):
    """
    "SPEAKER_00" -> "Speaker 1", "speaker 2" -> "Speaker 2"; real names are
    kept. Zero-based numbering (as in "SPEAKER_00") is shifted to start at 1.
    """
    name = (name or "").strip()
    match = GENERIC_SPEAKER.match(name)
    if not match:
        return name or None
    number = int(match.group(1)) + (1 if zero_based else 0)
    return f"Speaker {number}"


def _seconds(hours, minutes, seconds, millis):
    return (
        int(hours or 0) * 3600
        + int(minutes) * 60
        + int(seconds)
        + int(millis.ljust(3, "0")) / 1000
    )


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _join_turns(segments):
    """
    Turn [(speaker, text)] into a transcript. Consecutive segments from one
    speaker are merged; with speakers each turn is "Speaker: text".
    """
    turns = []
    for speaker, text in segments:
        text = " ".join(text.split())
        if not text:
            continue
        if turns and turns[-1][0] == speaker:
            turns[-1][1].append(text)
        else:
            turns.append((speaker, [text]))
    if any(speaker for speaker, _ in turns):
        return "\n\n".join(
            f"{speaker or 'Unknown'}: {' '.join(texts)}" for speaker, texts in turns
        )
    return " ".join(" ".join(texts) for _, texts in turns)


def parse_json_transcript(content):
    """Podcasting 2.0 JSON: {"segments": [{"speaker", "startTime", "endTime", "body"}]}."""
    data = json.loads(content)
    segments = data.get("segments", []) if isinstance(data, dict) else []
    zero_based = _zero_based(s.get("speaker") for s in segments if isinstance(s, dict))
    parsed, end = [], None
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        parsed.append(
            (
                normalize_speaker(segment.get("speaker"), zero_based),
                segment.get("body") or "",
            )
        )
        end_time = _to_float(segment.get("endTime"))
        if end_time is not None:
            end = max(end or 0, end_time)
    return parsed, end


def parse_cue_transcript(content):
    """
    WebVTT or SRT cues. VTT voice tags (<v Name>) become speakers; a cue
    without one continues the previous speaker, as captioning tools only tag
    some cues.
    """
    blocks = re.split(r"\n\s*\n", content.replace("\r\n", "\n"))
    raw, end, speaker = [], None, None
    for block in blocks:
        lines = block.strip().split("\n")
        for index, line in enumerate(lines):
            match = CUE_TIME.search(line)
            if not match:
                continue
            end = max(end or 0, _seconds(*match.groups()[4:]))
            text = " ".join(lines[index + 1 :])
            voice = VOICE.search(text)
            if voice:
                speaker = voice.group(1)
            raw.append((speaker, TAG.sub("", text)))
            break
    zero_based = _zero_based(name for name, _ in raw)
    return [(normalize_speaker(name, zero_based), text) for name, text in raw], end


def parse_transcript(content, fmt):
    """Parse one downloaded transcript. Returns (text, has_speakers, end_seconds)."""
    if fmt == "json":
        segments, end = parse_json_transcript(content)
    elif fmt in ("vtt", "srt"):
        segments, end = parse_cue_transcript(content)
    else:
        return " ".join(content.split()), False, None
    has_speakers = len({speaker for speaker, _ in segments if speaker}) > 1
    if not has_speakers:
        segments = [(None, text) for _, text in segments]
    return _join_turns(segments), has_speakers, end


# --- Choosing --------------------------------------------------------------


def is_usable(transcript, duration_seconds):
    """Does this transcript plausibly cover the whole episode?"""
    if transcript.words < MIN_WORDS:
        return False
    if not duration_seconds:
        return True
    if transcript.end_seconds:
        return transcript.end_seconds >= duration_seconds * MIN_COVERAGE
    return transcript.words >= duration_seconds / 60 * MIN_WORDS_PER_MINUTE


def ranked_links(links):
    """Readable links, best format first."""
    readable = [
        (FORMAT_RANK[link["type"]], link)
        for link in links or []
        if link.get("type") in FORMAT_RANK
    ]
    readable.sort(key=lambda pair: pair[0][1])
    return [(fmt, link["url"]) for (fmt, _), link in readable]


def fetch_transcript(url, fmt):
    """Download and parse one transcript file. Returns PublisherTranscript or None."""
    try:
        resp = requests.get(
            url,
            timeout=settings.HTTP_TIMEOUT,
            headers={"User-Agent": USER_AGENT},
            stream=True,
        )
        resp.raise_for_status()
        body = resp.raw.read(MAX_TRANSCRIPT_BYTES + 1, decode_content=True)
        if len(body) > MAX_TRANSCRIPT_BYTES:
            logger.warning(f"Transcript too large, skipping: {url}")
            return None
        content = body.decode(resp.encoding or "utf-8", errors="replace")
        text, has_speakers, end = parse_transcript(content, fmt)
    except (requests.RequestException, ValueError) as e:
        logger.warning(f"Could not read transcript {url}: {e}")
        return None
    return PublisherTranscript(
        text=text,
        format=fmt,
        url=url,
        has_speakers=has_speakers,
        end_seconds=end,
        words=len(text.split()),
    )


def best_publisher_transcript(episode):
    """
    The best usable transcript the publisher lists for this episode, preferring
    one with speaker turns. None if there is none or none covers the episode.
    """
    duration = episode.duration.total_seconds() if episode.duration else None
    fallback = None
    for fmt, url in ranked_links(episode.transcript_links)[:MAX_CANDIDATES]:
        transcript = fetch_transcript(url, fmt)
        if transcript is None or not is_usable(transcript, duration):
            if transcript is not None:
                logger.info(
                    f"Publisher transcript doesn't cover episode {episode.id}: {url}"
                )
            continue
        if transcript.has_speakers:
            return transcript
        fallback = fallback or transcript
    return fallback


def podcast_publishes_transcripts(podcast, exclude_id=None):
    """True when most of the podcast's recent episodes list a transcript."""
    recent = list(
        podcast.episodes.exclude(pk=exclude_id)
        .order_by("-release_date")
        .values_list("transcript_links", flat=True)[:RECENT_EPISODES]
    )
    if not recent:
        return False
    return sum(1 for links in recent if links) / len(recent) >= PUBLISHES_SHARE


def should_wait_for_publisher(episode, now=None, publishes_cache=None):
    """
    Hold off speech-to-text for a new episode of a podcast that usually
    publishes transcripts: hosts like Transistor add them after release.
    publishes_cache (podcast id -> bool) saves a query per episode in a run.
    """
    hours = config.PUBLISHER_TRANSCRIPT_WAIT_HOURS
    if hours <= 0 or episode.transcript_links or not episode.release_date:
        return False
    now = now or timezone.now()
    if now - episode.release_date >= timedelta(hours=hours):
        return False
    if publishes_cache is None:
        return podcast_publishes_transcripts(episode.podcast, exclude_id=episode.pk)
    if episode.podcast_id not in publishes_cache:
        publishes_cache[episode.podcast_id] = podcast_publishes_transcripts(
            episode.podcast
        )
    return publishes_cache[episode.podcast_id]


def apply_publisher_transcript(episode, transcript):
    """
    Save a publisher transcript. An episode waiting for batch speech-to-text
    has its workflow resumed instead.
    """
    from audio_processing.models import Episode
    from audio_processing.tasks.episode_tasks import process_complete_workflow

    episode.transcript = transcript.text
    episode.transcript_source = transcript.source
    fields = ["transcript", "transcript_source", "updated_at"]
    resume = (
        episode.processing_status == Episode.ProcessingStatus.QUEUED
        and episode.processing_step == Episode.BATCH_PENDING_STEP
    )
    if resume:
        episode.processing_step = ""
        fields.append("processing_step")
    episode.save(update_fields=fields)
    logger.info(
        f"Used publisher transcript ({transcript.format}, "
        f"speakers={transcript.has_speakers}) for episode {episode.id}"
    )
    if resume:
        process_complete_workflow.delay(episode.id)
    else:
        # Unprocessed episodes get no workflow run, so index the transcript
        # here; otherwise search would only ever see their show notes.
        episode.index_to_search()


def resolve_batch_pending(episodes):
    """
    For episodes waiting for batch speech-to-text: use a publisher transcript
    where there is one, and hold back those worth waiting for.
    Returns the ids to leave out of this batch run.
    """
    hold = set()
    now = timezone.now()
    publishes_cache = {}
    for episode in episodes:
        if episode.transcript_links:
            transcript = best_publisher_transcript(episode)
            if transcript:
                apply_publisher_transcript(episode, transcript)
                hold.add(episode.id)
                continue
        elif should_wait_for_publisher(episode, now, publishes_cache):
            hold.add(episode.id)
    return hold


def find_publisher_transcripts(max_episodes=200, recent_days=14):
    """
    The hourly job. Re-read feeds of active podcasts that have recent episodes
    without a transcript, to pick up transcripts published after release, then
    use publisher transcripts for any episode that lists one and has none,
    newest first (this also covers the archive of a newly added podcast).
    """
    from audio_processing.models import Episode, Podcast

    since = timezone.now() - timedelta(days=recent_days)
    missing = Episode.objects.filter(Q(transcript__isnull=True) | Q(transcript=""))
    podcasts = Podcast.objects.filter(
        is_active=True,
        episodes__in=missing.filter(release_date__gte=since),
    ).distinct()
    refreshed = 0
    for podcast in podcasts:
        if podcast.refresh_transcript_links() is not None:
            refreshed += 1

    candidates = (
        missing.filter(podcast__is_active=True)
        .exclude(transcript_links=[])
        .filter(publisher_transcript_checked_at__isnull=True)
        .exclude(processing_status=Episode.ProcessingStatus.RUNNING)
        .exclude(processing_step=Episode.BATCH_SUBMITTED_STEP)
        .order_by("-release_date")[:max_episodes]
    )
    applied = 0
    for episode in candidates:
        transcript = best_publisher_transcript(episode)
        if transcript:
            apply_publisher_transcript(episode, transcript)
            applied += 1
        else:
            # Don't download it again every hour; a feed refresh that changes
            # the links clears this.
            episode.publisher_transcript_checked_at = timezone.now()
            episode.save(update_fields=["publisher_transcript_checked_at"])
    result = {"feeds_refreshed": refreshed, "transcripts_applied": applied}
    logger.info(f"Publisher transcript search: {result}")
    return result
