import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)


class SearchableMixin:
    """
    Mixin to provide search indexing functionality for models.
    
    Models using this mixin should implement get_search_document() method
    to define what data should be indexed.
    """
    
    def index_to_search(self, index_uid=None):
        """
        Index this instance's data to Meilisearch for search functionality.
        
        Args:
            index_uid (str): The Meilisearch index to post to. 
                           If None, uses the model's default index.
            
        Returns:
            dict: Response from Meilisearch API or None if failed
        """
        try:
            # Get the index UID - either provided or use model's default
            if index_uid is None:
                index_uid = getattr(self, 'SEARCH_INDEX_UID', self._meta.model_name + 's')
            
            # Get document data from the model
            document = self.get_search_document()
            if not document:
                logger.warning(f"No search document data available for indexing: {self}")
                return None
            
            # Construct the endpoint URL
            endpoint_url = f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/{index_uid}/documents"

            # Prepare headers
            headers = {
                "Content-Type": "application/json",
                "Authorization": f'Bearer {settings.MEILISEARCH_API_KEY}'
            }
            
            # Make the API request
            logger.info(f"Indexing {self._meta.model_name} to Meilisearch: {self}...")
            response = requests.post(endpoint_url, headers=headers, json=[document], timeout=30)
            response.raise_for_status()
            
            result = response.json()
            logger.info(f"Successfully indexed {self._meta.model_name} to Meilisearch: {result}")
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to index {self._meta.model_name} to Meilisearch (HTTP error): {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Failed to index {self._meta.model_name} to Meilisearch: {str(e)}")
            return None
    
    def get_search_document(self):
        """
        Override this method in your model to define what data should be indexed.
        
        Returns:
            dict: Document data to be indexed, or None if not indexable
        """
        raise NotImplementedError(
            f"Model {self._meta.model_name} using SearchableMixin must implement get_search_document() method"
        )
    
    def remove_from_search(self, index_uid=None):
        """
        Remove this instance from the search index.
        
        Args:
            index_uid (str): The Meilisearch index to remove from.
                           If None, uses the model's default index.
            
        Returns:
            dict: Response from Meilisearch API or None if failed
        """
        try:
            # Get the index UID - either provided or use model's default
            if index_uid is None:
                index_uid = getattr(self, 'SEARCH_INDEX_UID', self._meta.model_name + 's')
            
            # Construct the endpoint URL
            endpoint_url = f"{settings.MEILISEARCH_URL.rstrip('/')}/indexes/{index_uid}/documents/{self.id}"

            # Prepare headers
            headers = {
                "Authorization": f'Bearer {settings.MEILISEARCH_API_KEY}'
            }
            
            # Make the API request
            logger.info(f"Removing {self._meta.model_name} from Meilisearch: {self}...")
            response = requests.delete(endpoint_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            result = response.json() if response.content else {"status": "deleted"}
            logger.info(f"Successfully removed {self._meta.model_name} from Meilisearch: {result}")
            return result
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to remove {self._meta.model_name} from Meilisearch (HTTP error): {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Failed to remove {self._meta.model_name} from Meilisearch: {str(e)}")
            return None
