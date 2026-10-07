import json
import logging
import re

from constance import config
from django.db import models
from django.db.models import JSONField

from audio_processing.models.mixins import GroqMixin
from audio_processing.prompts import get_topic_selection_prompt

logger = logging.getLogger(__name__)

# Title and show notes are enough to place an episode; cap the prompt size.
MAX_EPISODE_TEXT_CHARS = 4000


class Topic(models.Model, GroqMixin):
    topic_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True)
    top_words = JSONField(
        blank=True, null=True, help_text="List of top words or phrases for this topic"
    )
    is_enabled = models.BooleanField(
        default=True, help_text="Whether this topic is visible on the frontend"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Topic"
        verbose_name_plural = "Topics"

    def __str__(self):
        return self.name

    @classmethod
    def set_episodes_topics(cls):
        from audio_processing.models import Episode

        if not cls.objects.exists():
            logger.info("No topics available to tag episodes")
            return []

        for episode in Episode.objects.all():
            cls.set_episode_topics(episode)
        return

    @classmethod
    def set_episode_topics(cls, episode):
        """
        Ask Groq to pick the best-fitting topic for the episode from the topic list,
        and add it to the episode. Returns the Topic, or None if nothing fit.
        """
        if (
            not episode.title
            and not episode.description
            and not episode.content_encoded
        ):
            return None  # Skip episodes with no text content

        topics = list(cls.objects.all())
        if not topics:
            logger.info("No topics available to tag episodes")
            return None

        topic_list = [
            {
                "id": topic.id,
                "name": topic.name,
                "description": topic.description
                or ", ".join((topic.top_words or [])[:10]),
            }
            for topic in topics
        ]
        episode_text = "\n\n".join(
            part
            for part in (episode.title, episode.description, episode.content_encoded)
            if part
        )[:MAX_EPISODE_TEXT_CHARS]

        response = topics[0].get_groq_completion(
            get_topic_selection_prompt(topic_list, episode_text),
            model=config.TAG_MODEL,
            max_tokens=50,
            temperature=0,
        )
        topic_id = cls._parse_topic_id(response)
        if topic_id is None:
            return None

        topic_instance = next((t for t in topics if t.id == topic_id), None)
        if topic_instance is None:
            logger.warning(f"Model picked unknown topic id {topic_id}")
            return None

        episode.topics.add(topic_instance)
        logger.info(
            f"Tagged episode '{episode.title}' with topic '{topic_instance.name}'"
        )
        return topic_instance

    @staticmethod
    def _parse_topic_id(response):
        """Extract the topic id from the model's reply, tolerating code fences."""
        if not response:
            return None
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if not match:
            logger.warning(f"No JSON object in topic response: {response}")
            return None
        try:
            topic_id = json.loads(match.group(0)).get("topic_id")
        except (json.JSONDecodeError, AttributeError):
            logger.warning(f"Could not parse topic response: {response}")
            return None
        return topic_id if isinstance(topic_id, int) else None
