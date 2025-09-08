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
        
        # Process transcript using model method
        transcript = episode.generate_transcript()
        
        if transcript:
            logger.info(f"Episode transcript updated: {episode.title}")
            return {"success": True, "transcript_length": len(transcript)}
        else:
            logger.error(f"Failed to process transcript for: {episode.title}")
            return {"success": False, "error": "Failed to generate transcript"}
    
    except Episode.DoesNotExist:
        logger.error(f"Episode with ID {episode_id} not found")
        return {"success": False, "error": "Episode not found"}
    except Exception as e:
        logger.error(f"Error processing transcript for episode ID {episode_id}: {str(e)}")
        return {"success": False, "error": str(e)}

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
            logger.error(f"No tags applied for episode: {episode.title}")
            return {"success": False, "error": "No tags applied"}
    
    except Episode.DoesNotExist:
        logger.error(f"Episode with ID {episode_id} not found")
        return {"success": False, "error": "Episode not found"}
    except Exception as e:
        logger.error(f"Error suggesting tags for episode ID {episode_id}: {str(e)}")
        return {"success": False, "error": str(e)}

@shared_task
def extract_quotes(episode_id):
    """
    Celery task to extract quotes from an episode transcript.
    """
    logger.info(f"Extracting quotes for episode ID: {episode_id}")
    
    try:
        episode = Episode.objects.get(pk=episode_id)
        
        # Extract quotes using model method (from QuotableMixin)
        quotes = episode.extract_quotes()
        
        if quotes:
            logger.info(f"Extracted {len(quotes)} quotes from episode: {episode.title}")
            return {
                "success": True, 
                "quotes_extracted": len(quotes),
                "quote_ids": [quote.id for quote in quotes]
            }
        else:
            logger.warning(f"No quotes extracted for episode: {episode.title}")
            return {"success": True, "quotes_extracted": 0, "quote_ids": []}
    
    except Episode.DoesNotExist:
        logger.error(f"Episode with ID {episode_id} not found")
        return {"success": False, "error": "Episode not found"}
    except Exception as e:
        logger.error(f"Error extracting quotes for episode ID {episode_id}: {str(e)}")
        return {"success": False, "error": str(e)}
    
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
        logger.error(f"Episode with ID {episode_id} not found")
        return {"success": False, "error": "Episode not found"}
    except Exception as e:
        logger.error(f"Error in complete workflow for episode ID {episode_id}: {str(e)}")
        return {"success": False, "error": str(e)}
    
@shared_task
def extract_entities(episode_id):
    """
    Celery task to extract entities from an episode transcript.
    """
    logger.info(f"Extracting entities for episode ID: {episode_id}")

    try:
        episode = Episode.objects.get(pk=episode_id)

        # Extract entities using model method (from EntityMixin)
        entities = episode.extract_entities()

        if entities:
            logger.info(f"Extracted {len(entities)} entities from episode: {episode.title}")
            return {
                "success": True,
                "entities_extracted": len(entities),
                "entity_ids": [entity.id for entity in entities]
            }
        else:
            logger.warning(f"No entities extracted for episode: {episode.title}")
            return {"success": True, "entities_extracted": 0, "entity_ids": []}

    except Episode.DoesNotExist:
        logger.error(f"Episode with ID {episode_id} not found")
        return {"success": False, "error": "Episode not found"}
    except Exception as e:
        logger.error(f"Error extracting entities for episode ID {episode_id}: {str(e)}")
        return {"success": False, "error": str(e)}