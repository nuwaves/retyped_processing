import logging

from celery import shared_task

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

@shared_task
def reindex_all_entities_for_search():
	"""
	Celery task to reindex all entities for search.
	"""
	from audio_processing.models.entity import Entity
	entities = Entity.objects.all()
	for entity in entities:
		try:
			index_entity_for_search.delay(entity.id)
		except Exception as e:
			logger.error(f"Error indexing entity {entity.id}: {e}")
	return {'success': f"Reindexed {entities.count()} entities for search"}
