from django.db import models
from django.utils.translation import gettext_lazy as _
from audio_processing.models.mixins.groq_mixin import GroqMixin
from audio_processing.models.searchable_mixin import SearchableMixin
import json
from audio_processing.prompts import get_entity_extraction_prompt
import re

class Entity(models.Model, GroqMixin, SearchableMixin):
    class Meta:
        unique_together = ("name", "type")

    SEARCH_INDEX_UID = "entities"

    def get_search_document(self):
        """
        Returns a dictionary representing the entity for search indexing.
        """
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
    class EntityType(models.TextChoices):
        PERSON = 'PERSON', _('Person')
        ORGANIZATION = 'ORGANIZATION', _('Organization')
        PRODUCT = 'PRODUCT', _('Product')

    name = models.CharField(max_length=255)
    type = models.CharField(max_length=20, choices=EntityType.choices)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} ({self.type})"

    @classmethod
    def entities_from_text(cls, text, related_obj=None):
        """
        Calls Groq to extract entities from text, creates them if not exist,
        and associates them to related_obj (if provided, must have a ManyToMany to Entity).
        Returns a list of Entity instances.
        """
        prompt = get_entity_extraction_prompt(text)
        # Use GroqMixin to call Groq
        response = cls().get_groq_completion(prompt)
        entities = []
        if response:
            cleaned_response = response
            code_block_match = re.search(r'```json(.*?)```', cleaned_response, re.DOTALL | re.IGNORECASE)
            if code_block_match:
                cleaned_response = code_block_match.group(1)
            # If not found, fallback to removing any generic code block
            else:
                code_block_match = re.search(r'```(.*?)```', cleaned_response, re.DOTALL)
                if code_block_match:
                    cleaned_response = code_block_match.group(1)
            data = json.loads(response)
            for ent in data:
                name = ent.get('name')
                etype = ent.get('type')
                if name and etype in cls.EntityType.values:
                    entity, _ = cls.objects.get_or_create(name=name, type=etype)
                    entities.append(entity)
        # Associate entities to related_obj if provided
        if related_obj and hasattr(related_obj, 'entities'):
            related_obj.entities.add(*entities)
        return entities
        