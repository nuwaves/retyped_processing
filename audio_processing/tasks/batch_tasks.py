from audio_processing.models.processing_batch import ProcessingBatch
from celery import shared_task
from audio_processing.models.processing_batch import ProcessingBatch

@shared_task
def fetch_and_apply_groq_results_task(batch_id):
	"""
	Celery task to fetch Groq batch results and update episodes for a ProcessingBatch.
	"""
	batch = ProcessingBatch.objects.get(pk=batch_id)
	return batch.fetch_and_apply_groq_results()

@shared_task
def process_pending_batches_task():
	"""
	Celery task to process all pending ProcessingBatch jobs from the last week.
	"""
	return ProcessingBatch.process_pending_batches()