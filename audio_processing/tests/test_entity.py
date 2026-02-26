import pytest
from django.db import IntegrityError

from audio_processing.models.entity import Entity


@pytest.mark.django_db
def test_entity_creation():
    e = Entity.objects.create(name="John Doe", type=Entity.EntityType.PERSON)
    assert e.name == "John Doe"
    assert e.type == Entity.EntityType.PERSON

@pytest.mark.django_db
def test_entity_unique_name():
    Entity.objects.create(name="Acme Corp", type=Entity.EntityType.ORGANIZATION)
    with pytest.raises(IntegrityError):
        Entity.objects.create(name="Acme Corp", type=Entity.EntityType.ORGANIZATION)

@pytest.mark.django_db
def test_entities_from_text_creates_entities(monkeypatch):
    text = "John Doe founded Acme Corp to sell Acme Widget."
    # Patch GroqMixin.get_groq_completion to return a fixed response
    monkeypatch.setattr(Entity, "get_groq_completion", lambda self, prompt, **kwargs: '[{"name": "John Doe", "type": "PERSON"}, {"name": "Acme Corp", "type": "ORGANIZATION"}, {"name": "Acme Widget", "type": "PRODUCT"}]')
    entities = Entity.entities_from_text(text)
    names = [e.name for e in entities]
    types = [e.type for e in entities]
    assert set(names) == {"John Doe", "Acme Corp", "Acme Widget"}
    assert set(types) == {Entity.EntityType.PERSON, Entity.EntityType.ORGANIZATION, Entity.EntityType.PRODUCT}

@pytest.mark.django_db
def test_entities_from_text_associates_to_related_obj(monkeypatch):
    class DummyRelated:
        def __init__(self):
            self.entities = DummyM2M()
    class DummyM2M:
        def __init__(self):
            self.added = []
        def add(self, *args):
            self.added.extend(args)
    text = "John Doe founded Acme Corp."
    monkeypatch.setattr(Entity, "get_groq_completion", lambda self, prompt, **kwargs: '[{"name": "John Doe", "type": "PERSON"}, {"name": "Acme Corp", "type": "ORGANIZATION"}]')
    related = DummyRelated()
    entities = Entity.entities_from_text(text, related_obj=related)
    assert len(related.entities.added) == 2
    assert all(isinstance(e, Entity) for e in related.entities.added)
