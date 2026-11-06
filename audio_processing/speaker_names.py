"""
Name the speakers in a transcript that already marks who is talking.

Publisher transcripts (see transcript_manager) arrive with turns labelled
"Speaker 1:", "Speaker 2:" and so on. Rewriting the whole transcript with an
LLM to add names is slow, costly and lets the model move lines between
speakers. Instead the LLM sees a few lines from each speaker plus the show
and episode descriptions, says who each label is, and the labels are
replaced in code. Who said what stays exactly as the publisher marked it.
"""

import json
import logging
import re

from constance import config

from audio_processing.prompts import get_speaker_names_prompt

logger = logging.getLogger(__name__)

# "Speaker 3: ..." or "John Coogan: ..." opening a paragraph.
TURN = re.compile(r"^([^:\n]{1,60}):\s", re.MULTILINE)
GENERIC_LABEL = re.compile(r"^(Speaker \d+|Unknown)$")

# Opening of the episode, where hosts usually introduce themselves and guests.
INTRO_CHARS = 6000
SAMPLES_PER_SPEAKER = 6
SAMPLE_CHARS = 400
NAMES_MAX_TOKENS = 1000
MAX_NAME_CHARS = 60


def turns(transcript):
    """Split a "Label: text" transcript into [(label, text)] by paragraph."""
    result = []
    for paragraph in transcript.split("\n\n"):
        match = TURN.match(paragraph)
        if not match:
            return None
        result.append((match.group(1), paragraph[match.end() :].strip()))
    return result


def has_speaker_turns(episode):
    """
    Is this a publisher transcript where every paragraph names its speaker?
    Speech-to-text transcripts are one block of text and still need the
    full rewrite.
    """
    if not (episode.transcript_source or "").startswith("publisher:"):
        return False
    parsed = turns(episode.transcript or "")
    return bool(parsed) and len({label for label, _ in parsed}) > 1


def speaker_samples(parsed):
    """
    Up to SAMPLES_PER_SPEAKER lines for each generic label, longest first,
    with each speaker's share of the words. Returns {label: {...}}.
    """
    by_label = {}
    for label, text in parsed:
        if GENERIC_LABEL.match(label) and label != "Unknown":
            by_label.setdefault(label, []).append(text)
    total = sum(len(t.split()) for _, t in parsed) or 1
    samples = {}
    for label, texts in by_label.items():
        words = sum(len(t.split()) for t in texts)
        longest = sorted(texts, key=len, reverse=True)[:SAMPLES_PER_SPEAKER]
        samples[label] = {
            "share": round(100 * words / total),
            "lines": [t[:SAMPLE_CHARS] for t in longest],
        }
    return samples


NOT_A_NAME = {"null", "none", "unknown", "n/a", "na", "host", "guest", "narrator"}


def _contains(text, word):
    word = word.strip(".,'\"")
    return len(word) >= 2 and re.search(
        rf"\b{re.escape(word)}\b", text or "", re.IGNORECASE
    )


def mentioned(name, evidence, show_name=""):
    """
    Was this person in what the model was shown? Their surname must appear,
    or their first name must be in the show's name ("Dwarkesh Podcast").
    Guards against invented names for speakers nobody introduces.
    """
    words = name.split()
    return bool(
        _contains(evidence, words[-1])
        or (len(words) > 1 and _contains(show_name, words[0]))
    )


def parse_names(content, labels, evidence=None, show_name=""):
    """
    Read the model's {"Speaker 1": "Name" | null} answer. Keeps only labels
    that were asked about and plausible names that appear in the evidence
    (the prompt) when given; anything else stays generic.
    """
    if not content:
        return None
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    names = {}
    for label in labels:
        name = data.get(label)
        if not isinstance(name, str):
            continue
        name = " ".join(name.split())
        if (
            name
            and len(name) <= MAX_NAME_CHARS
            and ":" not in name
            and not GENERIC_LABEL.match(name)
            and name.lower() not in NOT_A_NAME
            and (evidence is None or mentioned(name, evidence, show_name))
        ):
            names[label] = name
    return names


def apply_names(transcript, names):
    """Replace "Speaker N:" at the start of each turn with the matched name."""
    if not names:
        return transcript

    def rename(match):
        return f"{names.get(match.group(1), match.group(1))}: "

    return TURN.sub(rename, transcript)


def name_speakers(episode):
    """
    Build the speaker script for a transcript with marked turns. Returns the
    script, or None when the model call fails (so the step can be retried).
    """
    parsed = turns(episode.transcript)
    samples = speaker_samples(parsed)
    if not samples:
        # Every speaker is already named.
        return episode.transcript

    prompt = get_speaker_names_prompt(
        episode, episode.transcript[:INTRO_CHARS], samples
    )
    content = episode.get_groq_completion(
        prompt=prompt,
        model=getattr(config, "SPEAKER_MODEL", None),
        max_tokens=NAMES_MAX_TOKENS,
        temperature=0.1,
    )
    # Descriptions and transcript lines only, not the prompt's own example.
    evidence = prompt.split("\nGuidelines:")[0]
    names = parse_names(
        content, samples, evidence=evidence, show_name=episode.podcast.name
    )
    if names is None:
        logger.warning(f"Could not read speaker names for episode {episode.id}")
        return None
    unnamed = sorted(set(samples) - set(names))
    logger.info(
        f"Matched speakers for episode {episode.id}: {names}"
        + (f"; left unnamed: {unnamed}" if unnamed else "")
    )
    return apply_names(episode.transcript, names)
