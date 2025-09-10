from celery import shared_task
from audio_processing.models import Episode
import logging

logger = logging.getLogger(__name__)


@shared_task
def add_transcript(episode_id):
    """
    Celery task to process an episode and generate transcript.
    """
    logger.info(f"Processing transcript for episode ID: {episode_id}")
    
    try:
        episode = Episode.objects.get(pk=episode_id)
        transcript = episode.generate_transcript()
        if transcript:
            logger.info(f"Episode transcript updated: {episode.title}")
            return {"success": True, "transcript_length": len(transcript)}
        else:
            error_msg = "Failed to generate transcript"
            logger.error(f"{error_msg} for: {episode.title}")
            episode.error = error_msg
            episode.save(update_fields=["error"])
            return {"success": False, "error": error_msg}
    except Episode.DoesNotExist:
        error_msg = "Episode not found"
        logger.error(f"Episode with ID {episode_id} not found")
        # Can't save error to episode since it doesn't exist
        return {"success": False, "error": error_msg}
    except Exception as e:
        error_msg = f"Error processing transcript: {str(e)}"
        logger.error(error_msg)
        try:
            episode = Episode.objects.get(pk=episode_id)
            episode.error = error_msg
            episode.save(update_fields=["error"])
        except Exception:
            pass
        return {"success": False, "error": error_msg}

@shared_task
def suggest_and_apply_tags(episode_id):
    """
    Celery task to suggest and apply tags to an episode.
    """
    logger.info(f"Suggesting tags for episode ID: {episode_id}")
    
    try:
        episode = Episode.objects.get(pk=episode_id)
        applied_tags = episode.suggest_and_apply_tags()
        if applied_tags is not None:
            logger.info(f"Applied {len(applied_tags)} tags to episode: {episode.title}")
            return {"success": True, "applied_tags": len(applied_tags)}
        else:
            error_msg = "No tags applied"
            logger.error(f"{error_msg} for episode: {episode.title}")
            episode.error = error_msg
            episode.save(update_fields=["error"])
            return {"success": False, "error": error_msg}
    except Episode.DoesNotExist:
        error_msg = "Episode not found"
        logger.error(f"Episode with ID {episode_id} not found")
        return {"success": False, "error": error_msg}
    except Exception as e:
        error_msg = f"Error suggesting tags: {str(e)}"
        logger.error(error_msg)
        try:
            episode = Episode.objects.get(pk=episode_id)
            episode.error = error_msg
            episode.save(update_fields=["error"])
        except Exception:
            pass
        return {"success": False, "error": error_msg}

@shared_task
def extract_quotes(episode_id):
    """
    Celery task to extract quotes from an episode transcript.
    """
    logger.info(f"Extracting quotes for episode ID: {episode_id}")
    
    try:
        episode = Episode.objects.get(pk=episode_id)
        quotes = episode.extract_quotes()
        if quotes:
            logger.info(f"Extracted {len(quotes)} quotes from episode: {episode.title}")
            return {
                "success": True,
                "quotes_extracted": len(quotes),
                "quote_ids": [quote.id for quote in quotes]
            }
        else:
            error_msg = "No quotes extracted"
            logger.warning(f"{error_msg} for episode: {episode.title}")
            episode.error = error_msg
            episode.save(update_fields=["error"])
            return {"success": True, "quotes_extracted": 0, "quote_ids": []}
    except Episode.DoesNotExist:
        error_msg = "Episode not found"
        logger.error(f"Episode with ID {episode_id} not found")
        return {"success": False, "error": error_msg}
    except Exception as e:
        error_msg = f"Error extracting quotes: {str(e)}"
        logger.error(error_msg)
        try:
            episode = Episode.objects.get(pk=episode_id)
            episode.error = error_msg
            episode.save(update_fields=["error"])
        except Exception:
            pass
        return {"success": False, "error": error_msg}
    
@shared_task
def process_complete_workflow(episode_id):
    """
    Celery task to process the complete workflow for an episode:
    1. Generate transcript (if needed)
    2. Apply tags
    3. Generate speaker script
    4. Generate summary
    5. Extract quotes
    """
    logger.info(f"Starting complete workflow for episode ID: {episode_id}")
    
    try:
        episode = Episode.objects.get(pk=episode_id)
        result = episode.process_complete_workflow()
        logger.info(f"Completed workflow for episode: {episode.title}")
        return result
    except Episode.DoesNotExist:
        error_msg = "Episode not found"
        logger.error(f"Episode with ID {episode_id} not found")
        return {"success": False, "error": error_msg}
    except Exception as e:
        error_msg = f"Error in complete workflow: {str(e)}"
        logger.error(error_msg)
        try:
            episode = Episode.objects.get(pk=episode_id)
            episode.error = error_msg
            episode.save(update_fields=["error"])
        except Exception:
            pass
        return {"success": False, "error": error_msg}
    
@shared_task
def extract_entities(episode_id):
    """
    Celery task to extract entities from an episode transcript.
    """
    logger.info(f"Extracting entities for episode ID: {episode_id}")

    try:
        episode = Episode.objects.get(pk=episode_id)
        entities = episode.extract_entities()
        if entities:
            logger.info(f"Extracted {len(entities)} entities from episode: {episode.title}")
            return {
                "success": True,
                "entities_extracted": len(entities),
                "entity_ids": [entity.id for entity in entities]
            }
        else:
            error_msg = "No entities extracted"
            logger.warning(f"{error_msg} for episode: {episode.title}")
            episode.error = error_msg
            episode.save(update_fields=["error"])
            return {"success": True, "entities_extracted": 0, "entity_ids": []}
    except Episode.DoesNotExist:
        error_msg = "Episode not found"
        logger.error(f"Episode with ID {episode_id} not found")
        return {"success": False, "error": error_msg}
    except Exception as e:
        error_msg = f"Error extracting entities: {str(e)}"
        logger.error(error_msg)
        try:
            episode = Episode.objects.get(pk=episode_id)
            episode.error = error_msg
            episode.save(update_fields=["error"])
        except Exception:
            pass
        return {"success": False, "error": error_msg}