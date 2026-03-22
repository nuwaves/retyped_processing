import logging

from django.conf import settings
from django.db import models
from django.db.models import JSONField
from django.utils.text import slugify

from audio_processing.models.mixins import GroqMixin

if settings.HF_API_TOKEN:
    from bertopic import BERTopic
    from huggingface_hub import login

    login(settings.HF_API_TOKEN)
    loaded_model = BERTopic.load("itsCody/retyped-topic-model")
    logger = logging.getLogger(__name__)
else:
    loaded_model = None
    logger = logging.getLogger(__name__)
    logger.warning(
        "Hugging Face API token not found in settings. Topic modeling will be disabled."
    )


class Topic(models.Model, GroqMixin):
    topic_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    description = models.TextField(blank=True)
    top_words = JSONField(
        blank=True, null=True, help_text="List of top words or phrases for this topic"
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
    def load_all_topics_from_bert_topic_model(self):

        topics = loaded_model.get_topics()
        for topic_id, words in topics.items():
            try:
                if topic_id == -1:
                    continue  # Skip outlier topic
                top_words = [word for word, _ in words]
                topic = Topic(top_words=top_words)
                name = topic.get_groq_completion(
                    prompt=f"Generate a name for a topic based on the following top words or phrases: {', '.join(top_words)}. Do not respond with anything except for one single topic name, which should be two words or less",
                    max_tokens=50,
                )
                topic.name = name.strip().strip('"')
                topic.slug = slugify(topic.name)
                topic.topic_id = topic_id
                topic.save()
            except Exception as e:
                logger.error(
                    f"Failed to create topic for ID {topic_id}: {str(e)} with top words {top_words}"
                )
        return

    @classmethod
    def set_episodes_topics(cls):
        from audio_processing.models import Episode

        episodes = Episode.objects.all()
        topics = cls.objects.all()
        if not topics.exists():
            logger.info("No topics available to tag episodes")
            return []

        for episode in episodes:
            cls.set_episode_topics(episode)
        return

    @classmethod
    def set_episode_topics(cls, episode):
        if (
            not episode.title
            and not episode.description
            and not episode.content_encoded
        ):
            return  # Skip episodes with no text content
        episode_text = (
            f"{episode.title}\n\n{episode.description}\n\n{episode.content_encoded}"
        )
        topic = loaded_model.transform([episode_text])[0][0]
        if topic == -1:
            return  # Skip outlier topic
        try:
            topic_instance = cls.objects.get(topic_id=topic)
            episode.topics.add(topic_instance)
            episode.save()
            logger.info(
                f"Tagged episode '{episode.title}' with topic '{topic_instance.name}'"
            )
        except Exception as e:
            logger.error(f"Failed to tag episode '{episode.title}': {str(e)}")
        return
