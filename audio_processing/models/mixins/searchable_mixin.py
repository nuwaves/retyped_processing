import logging
import operator
from functools import reduce

from django.contrib.postgres.search import SearchVector
from django.db import transaction
from django.db.models import TextField, Value

logger = logging.getLogger(__name__)

# Postgres text-search configuration used for indexing and querying.
SEARCH_CONFIG = "english"

# A tsvector can't exceed 1MB. Cap each field so very long transcripts
# still index (the first 200k characters is several hours of speech).
MAX_FIELD_CHARS = 200_000


class SearchableMixin:
    """
    Keeps a model's Postgres full-text ``search_vector`` column up to date.

    Models using this mixin need a ``search_vector`` SearchVectorField
    (with a GIN index) and must implement get_search_fields().
    """

    def get_search_fields(self):
        """
        Return the text to index as a list of (text, weight) pairs.

        Weight is "A" (most important) through "D" (least important);
        it controls ranking, not whether a document matches.
        """
        raise NotImplementedError(
            f"Model {self._meta.model_name} using SearchableMixin must implement get_search_fields()"
        )

    def build_search_vector(self):
        """Return a SearchVector expression for this instance, or None."""
        parts = [
            SearchVector(
                Value(str(text)[:MAX_FIELD_CHARS], output_field=TextField()),
                weight=weight,
                config=SEARCH_CONFIG,
            )
            for text, weight in self.get_search_fields()
            if text
        ]
        if not parts:
            return None
        return reduce(operator.add, parts)

    def index_to_search(self):
        """
        Recompute and store this instance's search vector.

        Writes with a queryset update so it doesn't call save() (and its
        side effects) again. Runs in a savepoint so a failure here can't
        break the caller's transaction. Returns True on success.
        """
        if self.pk is None:
            return False
        try:
            with transaction.atomic():
                type(self)._base_manager.filter(pk=self.pk).update(
                    search_vector=self.build_search_vector()
                )
            return True
        except Exception as e:
            logger.error(
                f"Failed to index {self._meta.model_name} {self.pk} for search: {e}"
            )
            return False

    def remove_from_search(self):
        """Clear this instance's search vector so it no longer matches searches."""
        if self.pk is None:
            return False
        type(self)._base_manager.filter(pk=self.pk).update(search_vector=None)
        return True
