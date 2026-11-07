from datetime import timedelta

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from audio_processing.models import Episode, Podcast, Tag
from audio_processing.models.entity import Entity
from audio_processing.models.topic import Topic
from audio_processing.utils.related import related_episodes


class RelatedEpisodesTest(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.now = timezone.now()
        self.show = Podcast.objects.create(name="Show A", url="https://example.com/a")
        self.other_show = Podcast.objects.create(
            name="Show B", url="https://example.com/b"
        )
        self.source = self._episode("source", self.show, days_ago=0)

    def _episode(self, slug, podcast, days_ago=1, summary="A summary."):
        return Episode.objects.create(
            title=slug.title(),
            slug=slug,
            podcast=podcast,
            raw_audio_url=f"https://example.com/{slug}.mp3",
            summary=summary,
            release_date=self.now - timedelta(days=days_ago),
        )

    def _entity(self, name, type="PERSON"):
        return Entity.objects.create(name=name, type=type)

    def test_shared_entity_ranks_above_shared_tag(self):
        guest = self._entity("Niche Guest")
        tag = Tag.objects.create(name="AI", slug="ai")
        self.source.entities.add(guest)
        self.source.tags.add(tag)

        by_guest = self._episode("by-guest", self.other_show, days_ago=300)
        by_guest.entities.add(guest)
        by_tag = self._episode("by-tag", self.other_show, days_ago=1)
        by_tag.tags.add(tag)

        results = related_episodes(self.source, limit=5)

        self.assertEqual([ep.slug for ep in results][:2], ["by-guest", "by-tag"])
        self.assertNotIn(self.source, results)

    def test_rare_entity_outweighs_common_entity(self):
        rare = self._entity("Rare Founder")
        common = self._entity("Big Company", type="ORGANIZATION")
        self.source.entities.add(rare, common)
        for i in range(5):
            self._episode(f"common-{i}", self.other_show, days_ago=1).entities.add(
                common
            )
        rare_match = self._episode("rare-match", self.other_show, days_ago=1)
        rare_match.entities.add(rare)

        results = related_episodes(self.source, limit=1)

        self.assertEqual([ep.slug for ep in results], ["rare-match"])

    def test_skips_episodes_without_content(self):
        guest = self._entity("Guest")
        self.source.entities.add(guest)
        thin = self._episode("thin", self.other_show, summary="")
        thin.entities.add(guest)

        self.assertNotIn(thin, related_episodes(self.source))

    def test_caps_episodes_per_show(self):
        topic = Topic.objects.create(topic_id=1, name="Tech", slug="tech")
        self.source.topics.add(topic)
        for i in range(4):
            self._episode(f"b-{i}", self.other_show, days_ago=i + 1).topics.add(topic)
        third_show = Podcast.objects.create(name="Show C", url="https://example.com/c")
        self._episode("c-0", third_show, days_ago=30).topics.add(topic)

        results = related_episodes(self.source, limit=3)

        self.assertEqual(
            sum(1 for ep in results if ep.podcast_id == self.other_show.id), 2
        )
        self.assertIn("c-0", [ep.slug for ep in results])

    def test_falls_back_to_latest_from_same_show(self):
        older = self._episode("older", self.show, days_ago=10)
        newer = self._episode("newer", self.show, days_ago=2)

        results = related_episodes(self.source, limit=2)

        self.assertEqual(results, [newer, older])

    def test_endpoint_returns_episodes_topics_and_entities(self):
        topic = Topic.objects.create(topic_id=1, name="Tech", slug="tech")
        hidden = Topic.objects.create(
            topic_id=2, name="Hidden", slug="hidden", is_enabled=False
        )
        company = self._entity("Acme", type="ORGANIZATION")
        person = self._entity("Jane Doe")
        self.source.topics.add(topic, hidden)
        self.source.entities.add(company, person)
        match = self._episode("match", self.other_show)
        match.entities.add(person)

        url = reverse("v1:api-v1-episodes-related", kwargs={"slug": "source"})
        response = self.client.get(url, {"limit": 3})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["episodes"][0]["slug"], "match")
        self.assertEqual(data["episodes"][0]["podcast"]["slug"], self.other_show.slug)
        self.assertEqual([t["slug"] for t in data["topics"]], ["tech"])
        self.assertEqual([e["name"] for e in data["entities"]], ["Jane Doe", "Acme"])

    def test_endpoint_404_for_unknown_episode(self):
        url = reverse("v1:api-v1-episodes-related", kwargs={"slug": "nope"})
        self.assertEqual(self.client.get(url).status_code, 404)
