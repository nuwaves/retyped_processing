import json
import os
from datetime import timedelta

import requests
from django.conf import settings
from django.db import models
from django.utils import timezone

from audio_processing.models.episode import Episode


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

    def __str__(self):
        return (
            f"Batch {self.id} ({self.processing_state}) - {self.record_count} records"
        )

    def fetch_and_apply_groq_results(self):
        """
        Fetch Groq batch status, download results if complete, and update episodes with transcript data.
        Returns: dict with status and summary info.
        """

        groq_api_key = getattr(settings, "GROQ_API_KEY", os.environ.get("GROQ_API_KEY"))
        if not groq_api_key:
            raise Exception("GROQ_API_KEY not configured in settings or environment.")

        # 1. Fetch batch status
        batch_id = self.external_batch_id
        batch_url = f"https://api.groq.com/openai/v1/batches/{batch_id}"
        resp = requests.get(
            batch_url, headers={"Authorization": f"Bearer {groq_api_key}"}
        )
        resp.raise_for_status()
        batch_info = resp.json()
        status = batch_info.get("status")

        # 2. Handle terminal error states
        failed_statuses = {"failed", "cancelled", "expired"}
        if status in failed_statuses:
            self.processing_state = self.STATE_ERRORED
            self.error = f"Batch permanently failed with status: {status}"
            self.save(update_fields=["processing_state", "error", "updated_at"])
            return {"status": status, "error": self.error}

        # 3. If not completed, return status only
        if status != "completed":
            return {"status": status, "message": "Batch not completed yet."}

        output_file_id = batch_info.get("output_file_id")
        if not output_file_id:
            self.processing_state = self.STATE_ERRORED
            self.error = "No output_file_id found in completed batch."
            self.save(update_fields=["processing_state", "error", "updated_at"])
            return {"status": status, "error": self.error}

        # 3. Download output file
        files_url = f"https://api.groq.com/openai/v1/files/{output_file_id}/content"
        out_resp = requests.get(
            files_url, headers={"Authorization": f"Bearer {groq_api_key}"}, stream=True
        )
        out_resp.raise_for_status()

        # Save to temp file
        import tempfile

        with tempfile.NamedTemporaryFile(
            mode="w+b", suffix=".jsonl", delete=False
        ) as tmpfile:
            for chunk in out_resp.iter_content(chunk_size=8192):
                tmpfile.write(chunk)
            tmpfile.flush()
            tmpfile_path = tmpfile.name

        # 4. Parse results and update episodes
        updated = 0
        with open(tmpfile_path, encoding="utf-8") as f:
            for line in f:
                try:
                    data = json.loads(line)
                    custom_id = data.get("custom_id")
                    response = data.get("response", {})
                    error = data.get("error")
                    if error:
                        continue
                    # custom_id is like "episode-123"
                    if custom_id and custom_id.startswith("episode-"):
                        eid = int(custom_id.split("-", 1)[1])
                        transcript = None
                        # For audio transcription, transcript is in response['body']['text']
                        body = response.get("body", {})
                        transcript = body.get("text")
                        if transcript:
                            Episode.objects.filter(pk=eid).update(transcript=transcript)
                            updated += 1
                except Exception:
                    continue

        os.remove(tmpfile_path)
        self.processing_state = self.STATE_SUCCESSFUL
        self.save(update_fields=["processing_state", "updated_at"])
        return {"status": status, "updated": updated}

    @staticmethod
    def process_pending_batches():
        """
        Find all batches created in the last week that are not failed or completed and run fetch_and_apply_groq_results on each.
        Returns: list of dicts with batch id and result.
        """
        one_week_ago = timezone.now() - timedelta(days=7)
        pending_batches = ProcessingBatch.objects.filter(
            created_at__gte=one_week_ago, processing_state=ProcessingBatch.STATE_CREATED
        )
        results = []
        for batch in pending_batches:
            result = batch.fetch_and_apply_groq_results()
            results.append({"batch_id": batch.id, "result": result})
        return results
