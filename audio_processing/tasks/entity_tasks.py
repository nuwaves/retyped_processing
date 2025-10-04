from celery import shared_task
import logging

logger = logging.getLogger(__name__)

@shared_task
def index_entity_for_search(entity_id):
	"""
	Celery task to index a single entity for search (e.g., Meilisearch/Elasticsearch).
	"""
	from audio_processing.models.entity import Entity
	try:
		entity = Entity.objects.get(id=entity_id)
		entity.index_to_search()
	except Exception as e:
		logger.error(f"Error indexing entity {entity_id}: {e}")