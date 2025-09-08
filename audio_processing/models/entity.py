from django.db import models
from django.utils.translation import gettext_lazy as _
from audio_processing.models.groq_mixin import GroqMixin
import json
from audio_processing.prompts import get_entity_extraction_prompt

class Entity(models.Model, GroqMixin):
    class EntityType(models.TextChoices):
        PERSON = 'PERSON', _('Person')
        ORGANIZATION = 'ORGANIZATION', _('Organization')
        PRODUCT = 'PRODUCT', _('Product')

    name = models.CharField(max_length=255, unique=True)
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
        response = cls().get_groq_completion(prompt, max_tokens=800)
        entities = []
        if response:
            try:
                data = json.loads(response)
                for ent in data:
                    name = ent.get('name')
                    etype = ent.get('type')
                    if name and etype in cls.EntityType.values:
                        entity, _ = cls.objects.get_or_create(name=name, type=etype)
                        entities.append(entity)
            except Exception as e:
                # Log or handle parse error
                pass
        # Associate entities to related_obj if provided
        if related_obj and hasattr(related_obj, 'entities'):
            related_obj.entities.add(*entities)
        return entities
        