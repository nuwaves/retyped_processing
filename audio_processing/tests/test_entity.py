from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import TestCase

from audio_processing.models.entity import Entity


class EntityModelTest(TestCase):
    def test_entity_creation(self):
        e = Entity.objects.create(name="John Doe", type=Entity.EntityType.PERSON)
        self.assertEqual(e.name, "John Doe")
        self.assertEqual(e.type, Entity.EntityType.PERSON)

    def test_entity_unique_name(self):
        Entity.objects.create(name="Acme Corp", type=Entity.EntityType.ORGANIZATION)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Entity.objects.create(name="Acme Corp", type=Entity.EntityType.ORGANIZATION)


class EntitiesFromTextTest(TestCase):
    def test_entities_from_text_creates_entities(self):
        text = "John Doe founded Acme Corp to sell Acme Widget."
        with patch.object(
            Entity,
            "get_groq_completion",
            return_value='[{"name": "John Doe", "type": "PERSON"}, {"name": "Acme Corp", "type": "ORGANIZATION"}, {"name": "Acme Widget", "type": "PRODUCT"}]',
        ):
            entities = Entity.entities_from_text(text)
        names = [e.name for e in entities]
        types = [e.type for e in entities]
        self.assertEqual(set(names), {"John Doe", "Acme Corp", "Acme Widget"})
        self.assertEqual(
            set(types),
            {
                Entity.EntityType.PERSON,
                Entity.EntityType.ORGANIZATION,
                Entity.EntityType.PRODUCT,
            },
        )

    def test_entities_from_text_associates_to_related_obj(self):
        class DummyM2M:
            def __init__(self):
                self.added = []

            def add(self, *args):
                self.added.extend(args)

        class DummyRelated:
            def __init__(self):
                self.entities = DummyM2M()

        text = "John Doe founded Acme Corp."
        related = DummyRelated()
        with patch.object(
            Entity,
            "get_groq_completion",
            return_value='[{"name": "John Doe", "type": "PERSON"}, {"name": "Acme Corp", "type": "ORGANIZATION"}]',
        ):
            Entity.entities_from_text(text, related_obj=related)
        self.assertEqual(len(related.entities.added), 2)
        self.assertTrue(all(isinstance(e, Entity) for e in related.entities.added))
