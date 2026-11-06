import logging
import os
import re
import tempfile
from pathlib import Path

import requests
from constance import config
from django.conf import settings

from audio_processing.models.mixins.audio_chunking import transcribe_audio_in_chunks
from audio_processing.prompts import get_speaker_transcript_prompt
from audio_processing.utils.llm import post_chat_completion
from audio_processing.utils.storage import audio_download_url

# Seconds to wait for Groq to transcribe a whole file (up to 100 MB) in one request.
TRANSCRIPTION_TIMEOUT = 900

# Speaker scripts run close to the transcript's length; a typical hour-long
# episode needs about 11k output tokens.
SCRIPT_MAX_TOKENS = 16384

# Transcripts longer than this are formatted in parts. A script for one part
# then fits well inside SCRIPT_MAX_TOKENS (whole transcripts over ~50k chars
# came back cut off) and each request finishes far inside LLM_TIMEOUT.
SCRIPT_CHUNK_CHARS = 30000

# How much of the previous part's script is shown to the next part, so speaker
# labels carry over.
SCRIPT_CONTEXT_CHARS = 1500

# "Name: ..." at the start of a script line.
SPEAKER_LABEL = re.compile(r"^([A-Z][^:\n\[\]]{0,48}):", re.MULTILINE)

# Sentence ends we prefer to split a transcript at. Splitting right after a
# question puts the next speaker's answer at the start of the next part, so a
# part rarely opens in the middle of someone's turn.
QUESTION_END = re.compile(r"\?[\"')\]]*\s+")
SENTENCE_END = re.compile(r"[.!?][\"')\]]*\s+")

# Some models bold the speaker labels ("**Host:**"), which the site shows as
# literal asterisks.
BOLD_SPEAKER_LABEL = re.compile(r"^\*\*([^*\n]+?):?\*\*:?", re.MULTILINE)


def clean_speaker_labels(script):
    """Turn "**Name:**" or "**Name**:" at the start of a line into "Name:"."""
    return BOLD_SPEAKER_LABEL.sub(r"\1:", script)


def split_transcript(transcript, max_chars=SCRIPT_CHUNK_CHARS):
    """
    Split a transcript into parts of at most max_chars, breaking at a paragraph
    end, else after a question, else at a sentence end, in the second half of
    each part where there is one; else at whitespace, else hard at max_chars.
    """
    parts = []
    text = transcript.strip()
    while len(text) > max_chars:
        window = text[:max_chars]
        floor = max_chars // 2
        cut = window.rfind("\n\n", floor)
        if cut != -1:
            cut += 2
        else:
            ends = [m.end() for m in QUESTION_END.finditer(window, floor)] or [
                m.end() for m in SENTENCE_END.finditer(window, floor)
            ]
            if ends:
                cut = ends[-1]
            else:
                space = window.rfind(" ", floor)
                cut = space + 1 if space != -1 else max_chars
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        parts.append(text)
    return parts


def last_speaker(script):
    """The label of the last speaker line in a script, or "" if there is none."""
    labels = SPEAKER_LABEL.findall(script)
    return labels[-1].strip() if labels else ""


def speaker_labels(script):
    """Speaker labels in the order they first appear in a script."""
    seen = []
    for name in SPEAKER_LABEL.findall(script):
        name = name.strip()
        if name and name not in seen:
            seen.append(name)
    return seen


logger = logging.getLogger(__name__)


class GroqMixin:
    """
    Mixin providing Groq API integration for various LLM tasks.
    """

    def get_groq_completion(self, prompt, model=None, max_tokens=1000, temperature=0.3):
        """
        Generic method to get completions from the chat LLM (LLM_API_URL).

        Args:
            prompt (str): The prompt to send to the model
            model (str, optional): Model name, defaults to config.DEFAULT_MODEL
            max_tokens (int): Maximum tokens in response
            temperature (float): Temperature for response generation

        Returns:
            str: The completion content or None if failed
        """
        api_key = getattr(settings, "LLM_API_KEY", "")
        if not api_key:
            logger.error("LLM_API_KEY not configured")
            return None

        # Default model if none specified
        if model is None:
            model = config.DEFAULT_MODEL

        data = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }

        try:
            content = post_chat_completion(data, label=f"LLM request ({model})")
            content = content.strip()

            # Remove any <think> tags that might be present
            content = re.sub(
                r"<think>.*?</think>", "", content, flags=re.DOTALL
            ).strip()

            return content

        except requests.exceptions.RequestException as e:
            logger.error(f"LLM API request failed: {str(e)}")
            return None
        except (KeyError, IndexError) as e:
            logger.error(f"Unexpected LLM API response format: {str(e)}")
            return None

    def get_transcript_from_groq(self):
        """
        Get transcript from Groq Whisper API. If file >100MB, use AudioChunkingMixin to chunk, transcribe, and stitch together.
        Returns:
            str: The transcript text or None if failed
        """
        url = "https://api.groq.com/openai/v1/audio/transcriptions"
        api_key = getattr(settings, "GROQ_API_KEY", "")
        if not api_key:
            logger.error("GROQ_API_KEY not configured")
            return None
        headers = {"Authorization": f"Bearer {api_key}"}
        clean_url = audio_download_url(self.s3_audio_url)
        if clean_url is None:
            clean_url = self.clean_url(self.raw_audio_url)
        tmp_path = None
        try:
            with requests.get(clean_url, stream=True, timeout=300) as r:
                r.raise_for_status()
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    for chunk in r.iter_content(chunk_size=65536):
                        tmp.write(chunk)
                    tmp_path = tmp.name
            file_size = os.path.getsize(tmp_path)
            max_chunk_size = 100 * 1024 * 1024  # 100MB
            if file_size > max_chunk_size:
                # Use the mixin to chunk and transcribe
                result = transcribe_audio_in_chunks(Path(tmp_path))
                transcript = result.get("text", "")
            else:
                # Single file, send as usual
                with open(tmp_path, "rb"):
                    files = {
                        "url": (None, clean_url),
                        "model": (None, config.TEXT_TO_SPEECH_MODEL),
                        "language": (None, "en"),
                        "response_format": (None, "json"),
                    }
                    # Groq fetches and transcribes the whole file during this request.
                    response = requests.post(
                        url,
                        headers=headers,
                        files=files,
                        timeout=TRANSCRIPTION_TIMEOUT,
                    )
                    response.raise_for_status()
                    transcript = response.json().get("text", "")
            if transcript.strip():
                self.transcript = transcript
                self.save()
                logger.info(f"Transcript updated for: {self.raw_audio_url}")
                return transcript
            else:
                logger.warning(f"No transcript returned for: {self.raw_audio_url}")
                return None
        finally:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    def generate_speaker_script(self):
        """
        Use Groq LLM to convert the raw transcript into a formatted script with speaker identification.
        Returns the script transcript or None if failed.
        """
        # Validate transcript
        if not self._validate_transcript():
            return None

        logger.info(f"Generating speaker script for: {self.raw_audio_url}")

        try:
            # Long transcripts are formatted in parts, each continuing the last,
            # so the script isn't cut off at SCRIPT_MAX_TOKENS.
            parts = split_transcript(self.transcript)
            scripts = []
            for number, part in enumerate(parts, start=1):
                previous = "\n\n".join(scripts)
                prompt = get_speaker_transcript_prompt(
                    self,
                    transcript=part,
                    part=number,
                    total_parts=len(parts),
                    known_speakers=speaker_labels(previous),
                    previous_tail=previous[-SCRIPT_CONTEXT_CHARS:],
                    last_speaker=last_speaker(previous),
                )
                part_script = self.get_groq_completion(
                    prompt=prompt,
                    model=getattr(config, "SPEAKER_MODEL", None),
                    max_tokens=SCRIPT_MAX_TOKENS,
                    temperature=0.3,
                )
                if not part_script:
                    # A script with a gap in it is worse than none: leave the
                    # field empty so the backfill picks the episode up again.
                    logger.warning(
                        f"No script content returned for part {number}/{len(parts)}: {self.raw_audio_url}"
                    )
                    return None
                scripts.append(clean_speaker_labels(part_script))

            script_content = "\n\n".join(scripts)

            if script_content:
                self.script_transcript = script_content
                self.save()
                logger.info(f"Speaker script generated for: {self.raw_audio_url}")
                return script_content
            else:
                logger.warning(f"No script content returned for: {self.raw_audio_url}")
                return None

        except Exception as e:
            logger.error(f"Failed to generate speaker script: {str(e)}")
            return None

    def _validate_transcript(self):
        """
        Validate that the transcript exists and is suitable for processing.

        Returns:
            bool: True if transcript is valid, False otherwise
        """
        if not hasattr(self, "transcript") or not self.transcript:
            logger.warning(
                f"No transcript available for: {getattr(self, 'raw_audio_url', 'Unknown')}"
            )
            return False

        if not self.transcript.strip():
            logger.warning(
                f"Empty transcript for: {getattr(self, 'raw_audio_url', 'Unknown')}"
            )
            return False

        return True
