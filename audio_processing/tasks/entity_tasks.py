from celery import shared_task

@shared_task
def index_entity_for_search(entity_id):
	"""
	Celery task to index a single entity for search (e.g., Meilisearch/Elasticsearch).
	"""
	from audio_processing.models.entity import Entity
	try:
		entity = Entity.objects.get(id=entity_id)
		entity.index_to_search()
        return {'indexed': True, 'entity_id': entity_id}

    except Entity.DoesNotExist:
        return {'indexed': False, 'entity_id': entity_id, 'error': 'Entity not found'}

    except Exception as e:
        return {'indexed': False, 'entity_id': entity_id, 'error': str(e)}