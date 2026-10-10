from unittest.mock import patch

from django.test import TestCase

from audio_processing.models import Episode, Podcast, Topic


class SetEpisodeTopicsTest(TestCase):
    def setUp(self):
        self.podcast = Podcast.objects.create(
            name="Podcast", url="https://example.com/rss"
        )
        self.episode = Episode.objects.create(
            title="The economics of chip fabs",
            description="Why semiconductor plants cost $20B.",
            podcast=self.podcast,
            raw_audio_url="https://example.com/audio.mp3",
        )
        self.tech = Topic.objects.create(topic_id=1, name="Technology", slug="tech")
        self.food = Topic.objects.create(topic_id=2, name="Food", slug="food")

    def _pick(self, response):
        with patch.object(Topic, "get_groq_completion", return_value=response):
            return Topic.set_episode_topics(self.episode)

    def test_adds_the_topic_the_model_picks(self):
        topic = self._pick(f'{{"topic_id": {self.tech.id}}}')
        self.assertEqual(topic, self.tech)
        self.assertEqual(list(self.episode.topics.all()), [self.tech])

    def test_accepts_fenced_json(self):
        topic = self._pick(f'```json\n{{"topic_id": {self.food.id}}}\n```')
        self.assertEqual(topic, self.food)

    def test_null_topic_adds_nothing(self):
        self.assertIsNone(self._pick('{"topic_id": null}'))
        self.assertFalse(self.episode.topics.exists())

    def test_unknown_topic_id_adds_nothing(self):
        self.assertIsNone(self._pick('{"topic_id": 99999}'))
        self.assertFalse(self.episode.topics.exists())

    def test_unparseable_response_adds_nothing(self):
        self.assertIsNone(self._pick("Technology"))
        self.assertIsNone(self._pick(None))
        self.assertFalse(self.episode.topics.exists())

    def test_prompt_lists_topics_and_episode_text(self):
        with patch.object(
            Topic, "get_groq_completion", return_value='{"topic_id": null}'
        ) as completion:
            Topic.set_episode_topics(self.episode)
        prompt = completion.call_args.args[0]
        self.assertIn('"name": "Technology"', prompt)
        self.assertIn("The economics of chip fabs", prompt)

    def test_no_topics_skips_the_model(self):
        Topic.objects.all().delete()
        with patch.object(Topic, "get_groq_completion") as completion:
            self.assertIsNone(Topic.set_episode_topics(self.episode))
        completion.assert_not_called()
