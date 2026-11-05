import json
import logging
from datetime import timedelta

import requests
from django.conf import settings
from django.db import models
from django.utils import timezone

from audio_processing.models.episode import Episode

logger = logging.getLogger(__name__)

GROQ_API_URL = "https://api.groq.com/openai/v1"
TRANSCRIPTION_ENDPOINT = "/v1/audio/transcriptions"
# Groq suggests splitting big workloads into batches of about this many requests.
MAX_REQUESTS_PER_BATCH = 1000
# Cap on batches submitted per run, so one run can't flood Groq after a mass re-queue.
MAX_BATCHES_PER_RUN = 10
# Batch statuses after which Groq does no more work on the batch.
FINISHED_STATUSES = {"completed", "expired", "cancelled", "failed"}


def _groq_headers():
    api_key = getattr(settings, "GROQ_API_KEY", "")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not configured")
    return {"Authorization": f"Bearer {api_key}"}


class ProcessingBatch(models.Model):
    STATE_CREATED = "created"
    STATE_SUCCESSFUL = "successful"
    STATE_ERRORED = "errored"
    STATE_CHOICES = [
        (STATE_CREATED, "Created"),
        (STATE_SUCCESSFUL, "Successful"),
        (STATE_ERRORED, "Errored"),
    ]

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processing_state = models.CharField(
        max_length=32, choices=STATE_CHOICES, default=STATE_CREATED, db_index=True
    )
    error = models.TextField(
        blank=True, null=True, help_text="Error message if processing failed"
    )
    record_count = models.PositiveIntegerField(
        default=0, help_text="Number of records in this batch"
    )
    external_batch_id = models.CharField(
        max_length=128,
        blank=True,
        null=True,
        help_text="ID from external processing service",
    )
    episode_ids = models.JSONField(
        default=list, blank=True, help_text="Episodes transcribed by this batch"
    )

    def __str__(self):
        return (
            f"Batch {self.id} ({self.processing_state}) - {self.record_count} records"
        )

    @classmethod
    def submit_transcriptions(cls, episode_ids):
        """
        Upload a JSONL file with one transcription request per episode and start
        a Groq batch job for it. Returns the new ProcessingBatch.
        """
        episodes = list(Episode.objects.filter(pk__in=episode_ids))
        if not episodes:
            raise ValueError("No episodes to transcribe")
        lines = "".join(
            json.dumps(episode.batch_transcription_request()) + "\n"
            for episode in episodes
        )

        headers = _groq_headers()
        upload = requests.post(
            f"{GROQ_API_URL}/files",
            headers=headers,
            files={"file": ("transcriptions.jsonl", lines.encode("utf-8"))},
            data={"purpose": "batch"},
            timeout=settings.HTTP_TIMEOUT,
        )
        upload.raise_for_status()
        created = requests.post(
            f"{GROQ_API_URL}/batches",
            headers=headers,
            json={
                "input_file_id": upload.json()["id"],
                "endpoint": TRANSCRIPTION_ENDPOINT,
                "completion_window": "24h",
            },
            timeout=settings.HTTP_TIMEOUT,
        )
        created.raise_for_status()

        batch = cls.objects.create(
            external_batch_id=created.json()["id"],
            record_count=len(episodes),
            episode_ids=[episode.id for episode in episodes],
        )
        logger.info(
            f"Submitted Groq batch {batch.external_batch_id} for {len(episodes)} episodes"
        )
        return batch

    @classmethod
    def submit_pending_transcriptions(cls):
        """
        Put episodes queued for batch transcription into Groq batch jobs.
        Returns the batches created.
        """
        batches = []
        for _ in range(MAX_BATCHES_PER_RUN):
            ids = list(
                Episode.objects.filter(
                    processing_status=Episode.ProcessingStatus.QUEUED,
                    processing_step=Episode.BATCH_PENDING_STEP,
                )
                .order_by("processing_queued_at", "id")
                .values_list("id", flat=True)[:MAX_REQUESTS_PER_BATCH]
            )
            if not ids:
                break
            batch = cls.submit_transcriptions(ids)
            Episode.objects.filter(
                pk__in=ids, processing_step=Episode.BATCH_PENDING_STEP
            ).update(
                processing_step=Episode.BATCH_SUBMITTED_STEP,
                updated_at=timezone.now(),
            )
            batches.append(batch)
        return batches

    def fetch_and_apply_groq_results(self):
        """
        Check the Groq batch. Once Groq is done with it, save the transcripts it
        produced and queue the rest of the workflow for its episodes. Episodes
        that got no transcript (failed request, expired batch) are queued too;
        their workflow transcribes them with a direct request instead.
        """
        headers = _groq_headers()
        resp = requests.get(
            f"{GROQ_API_URL}/batches/{self.external_batch_id}",
            headers=headers,
            timeout=settings.HTTP_TIMEOUT,
        )
        resp.raise_for_status()
        batch_info = resp.json()
        status = batch_info.get("status")
        if status not in FINISHED_STATUSES:
            return {"status": status, "message": "Batch not completed yet."}

        updated = 0
        output_file_id = batch_info.get("output_file_id")
        if output_file_id:
            out_resp = requests.get(
                f"{GROQ_API_URL}/files/{output_file_id}/content",
                headers=headers,
                stream=True,
                timeout=settings.HTTP_TIMEOUT,
            )
            out_resp.raise_for_status()
            for line in out_resp.iter_lines():
                if line and self._apply_result_line(line):
                    updated += 1

        failed = len(self.episode_ids) - updated if self.episode_ids else 0
        if status == "completed":
            self.processing_state = self.STATE_SUCCESSFUL
            self.error = f"{failed} requests failed" if failed > 0 else None
        else:
            self.processing_state = self.STATE_ERRORED
            self.error = f"Batch ended with status: {status}"
        self.save(update_fields=["processing_state", "error", "updated_at"])
        resumed = self._resume_workflows()
        return {
            "status": status,
            "updated": updated,
            "resumed": resumed,
            "error": self.error,
        }

    @staticmethod
    def _apply_result_line(line):
        """Save the transcript from one output line. Returns True if one was saved."""
        try:
            data = json.loads(line)
            custom_id = data.get("custom_id") or ""
            response = data.get("response") or {}
            if data.get("error") or response.get("status_code") != 200:
                return False
            if not custom_id.startswith("episode-"):
                return False
            episode_id = int(custom_id.split("-", 1)[1])
            transcript = (response.get("body") or {}).get("text") or ""
        except (ValueError, AttributeError):
            logger.warning("Skipping unreadable Groq batch output line")
            return False
        if not transcript.strip():
            return False
        return bool(
            Episode.objects.filter(pk=episode_id).update(
                transcript=transcript, updated_at=timezone.now()
            )
        )

    def _resume_workflows(self):
        """Queue the workflow for this batch's episodes that are still waiting on it."""
        from audio_processing.tasks.episode_tasks import process_complete_workflow

        waiting = list(
            Episode.objects.filter(
                pk__in=self.episode_ids,
                processing_status=Episode.ProcessingStatus.QUEUED,
                processing_step=Episode.BATCH_SUBMITTED_STEP,
            ).values_list("id", flat=True)
        )
        Episode.objects.filter(pk__in=waiting).update(
            processing_step="", updated_at=timezone.now()
        )
        for episode_id in waiting:
            process_complete_workflow.delay(episode_id)
        return len(waiting)

    @staticmethod
    def process_pending_batches():
        """
        Check every unfinished batch from the last week and apply its results.
        Returns: list of dicts with batch id and result.
        """
        one_week_ago = timezone.now() - timedelta(days=7)
        pending_batches = ProcessingBatch.objects.filter(
            created_at__gte=one_week_ago, processing_state=ProcessingBatch.STATE_CREATED
        )
        results = []
        for batch in pending_batches:
            try:
                result = batch.fetch_and_apply_groq_results()
            except Exception as e:
                logger.error(f"Failed to check Groq batch {batch.id}: {e}")
                result = {"error": str(e)}
            results.append({"batch_id": batch.id, "result": result})
        return results

    @classmethod
    def run_transcription_batches(cls):
        """Submit waiting episodes in new batches, then apply finished batches."""
        submitted = cls.submit_pending_transcriptions()
        return {
            "submitted": [batch.id for batch in submitted],
            "checked": cls.process_pending_batches(),
        }
