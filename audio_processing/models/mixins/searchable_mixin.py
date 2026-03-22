import logging

from django.conf import settings
from meilisearch import Client

logger = logging.getLogger(__name__)


class SearchableMixin:
    """
    Mixin to provide search indexing functionality for models.

    Models using this mixin should implement get_search_document() method
    to define what data should be indexed.
    """

    def _get_meili_client(self):
        """
        Get the MeiliSearch client instance.

        Returns:
            Client: MeiliSearch client
        """
        return Client(settings.MEILISEARCH_URL, settings.MEILISEARCH_API_KEY)

    def index_to_search(self, index_uid=None, sync=True):
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
                index_uid = getattr(
                    self, "SEARCH_INDEX_UID", self._meta.model_name + "s"
                )

            # Get document data from the model
            document = self.get_search_document()
            if not document:
                logger.warning(
                    f"No search document data available for indexing: {self}"
                )
                return None

            client = self._get_meili_client()
            index = client.index(index_uid)

            # Make the API request
            logger.info(f"Indexing {self._meta.model_name} to Meilisearch: {self}...")
            task = index.add_documents([document])

            if sync:
                completed_task = client.wait_for_task(task.task_uid)
                logger.info(
                    f"Successfully indexed {self._meta.model_name} to Meilisearch: {completed_task}"
                )
                return completed_task
            else:
                logger.info(
                    f"Indexing {self._meta.model_name} to Meilisearch initiated: {task.task_uid}"
                )
                return {"task_uid": task.task_uid}

        except Exception as e:
            logger.error(
                f"Failed to index {self._meta.model_name} to Meilisearch: {str(e)}"
            )
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
                index_uid = getattr(
                    self, "SEARCH_INDEX_UID", self._meta.model_name + "s"
                )

            client = self._get_meili_client()
            index = client.index(index_uid)

            # Make the API request
            logger.info(f"Removing {self._meta.model_name} from Meilisearch: {self}...")
            result = index.delete_document(str(self.id))
            logger.info(
                f"Successfully removed {self._meta.model_name} from Meilisearch: {result}"
            )
            return result

        except Exception as e:
            logger.error(
                f"Failed to remove {self._meta.model_name} from Meilisearch: {str(e)}"
            )
            return None
