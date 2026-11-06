import json
from datetime import timedelta
from unittest.mock import patch

from constance.test import override_config
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from audio_processing import transcript_manager as tm
from audio_processing.models import Episode, Podcast

FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:podcast="https://podcastindex.org/namespace/1.0">
<channel><title>Show</title>
<item>
  <title>One</title>
  <guid>ep-1</guid>
  <enclosure url="https://cdn.example/1.mp3" type="audio/mpeg" length="1"/>
  <podcast:transcript url="https://t.example/1.vtt" type="text/vtt"/>
  <podcast:transcript url="https://t.example/1.json" type="application/json"/>
  <podcast:transcript url="https://t.example/1" type="text/html"/>
</item>
<item>
  <title>Two</title>
  <guid>ep-2</guid>
  <enclosure url="https://cdn.example/2.mp3" type="audio/mpeg" length="1"/>
</item>
</channel></rss>"""

JSON_TRANSCRIPT = json.dumps(
    {
        "version": "1.0.0",
        "segments": [
            {"speaker": "Speaker 1", "startTime": "0", "endTime": "2", "body": "Hi."},
            {"speaker": "Speaker 1", "startTime": "2", "endTime": "4", "body": "Hey."},
            {"speaker": "Speaker 2", "startTime": "4", "endTime": "9.5", "body": "Yo"},
        ],
    }
)

VTT = """WEBVTT

1
00:00:00.271 --> 00:00:02.232
<v SPEAKER_00> If you do everything, you'll win.

2
00:00:02.892 --> 00:00:06.059
<v SPEAKER_01>That is the maxim.

3
01:00:06.254 --> 01:00:07.921
<v SPEAKER_01>My guest today.
"""

SRT = """1
00:00:01,000 --> 00:00:02,500
Hello there

2
00:00:03,000 --> 00:00:04,000
general
"""


class ExtractLinksTest(SimpleTestCase):
    def test_reads_every_transcript_tag_keyed_by_guid_and_audio(self):
        links = tm.extract_transcript_links(FEED)
        self.assertEqual(len(links["ep-1"]), 3)
        self.assertEqual(links["ep-1"], links["https://cdn.example/1.mp3"])
        self.assertNotIn("ep-2", links)

    def test_refuses_entity_declarations_and_bad_xml(self):
        self.assertEqual(
            tm.extract_transcript_links(b"<!DOCTYPE x [<!ENTITY a 'b'>]><x/>"), {}
        )
        self.assertEqual(tm.extract_transcript_links(b"<rss><channel>"), {})

    def test_ranks_formats_and_skips_html(self):
        links = tm.extract_transcript_links(FEED)["ep-1"]
        self.assertEqual(
            tm.ranked_links(links),
            [("json", "https://t.example/1.json"), ("vtt", "https://t.example/1.vtt")],
        )


class ParseTranscriptTest(SimpleTestCase):
    def test_json_merges_turns(self):
        text, speakers, end = tm.parse_transcript(JSON_TRANSCRIPT, "json")
        self.assertEqual(text, "Speaker 1: Hi. Hey.\n\nSpeaker 2: Yo")
        self.assertTrue(speakers)
        self.assertEqual(end, 9.5)

    def test_vtt_voices_renumbered_from_one(self):
        text, speakers, end = tm.parse_transcript(VTT, "vtt")
        self.assertEqual(
            text,
            "Speaker 1: If you do everything, you'll win.\n\n"
            "Speaker 2: That is the maxim. My guest today.",
        )
        self.assertTrue(speakers)
        self.assertAlmostEqual(end, 3607.921)

    def test_untagged_vtt_cues_continue_the_previous_speaker(self):
        vtt = (
            "WEBVTT\n\n1\n00:00:00.269 --> 00:00:02.090\n<v SPEAKER_00> Thanks.\n\n"
            "2\n00:00:03.410 --> 00:00:05.011\nSo just in a second,\n\n"
            "3\n00:00:05.051 --> 00:00:07.892\n<v SPEAKER_02>Yeah.\n\n"
            "4\n00:00:07.912 --> 00:00:08.272\nI mean it.\n"
        )
        text, speakers, _ = tm.parse_transcript(vtt, "vtt")
        self.assertEqual(
            text,
            "Speaker 1: Thanks. So just in a second,\n\nSpeaker 3: Yeah. I mean it.",
        )
        self.assertTrue(speakers)

    def test_srt_without_speakers_is_plain_text(self):
        text, speakers, end = tm.parse_transcript(SRT, "srt")
        self.assertEqual(text, "Hello there general")
        self.assertFalse(speakers)
        self.assertEqual(end, 4.0)

    def test_real_names_kept_and_speaker_ten_not_renumbered(self):
        self.assertEqual(tm.normalize_speaker("John Coogan"), "John Coogan")
        self.assertFalse(tm._zero_based(["Speaker 10", "Speaker 1"]))
        self.assertTrue(tm._zero_based(["SPEAKER_00"]))


class IsUsableTest(SimpleTestCase):
    def _t(self, words, end=None):
        return tm.PublisherTranscript("w " * words, "json", "u", True, end, words)

    def test_coverage_by_timestamps(self):
        self.assertTrue(tm.is_usable(self._t(5000, end=3500), 3600))
        self.assertFalse(tm.is_usable(self._t(5000, end=1200), 3600))

    def test_coverage_by_word_rate_without_timestamps(self):
        self.assertTrue(tm.is_usable(self._t(4000), 3600))
        self.assertFalse(tm.is_usable(self._t(1000), 3600))

    def test_too_short(self):
        self.assertFalse(tm.is_usable(self._t(50), None))


class ManagerTest(TestCase):
    def setUp(self):
        self.podcast = Podcast.objects.create(name="Pod", url="https://pod.example/rss")

    def _episode(self, title, links=(), **extra):
        return Episode.objects.create(
            title=title,
            podcast=self.podcast,
            raw_audio_url=f"https://cdn.example/{title}.mp3",
            release_date=extra.pop("release_date", timezone.now()),
            duration=timedelta(seconds=10),
            transcript_links=list(links),
            **extra,
        )

    def _fake(self, has_speakers, fmt="json"):
        text = ("Speaker 1: " if has_speakers else "") + "word " * 300
        return tm.PublisherTranscript(text, fmt, "u", has_speakers, 9.5, 300)

    def test_prefers_a_transcript_with_speakers(self):
        episode = self._episode(
            "e",
            [
                {"url": "a", "type": "text/plain"},
                {"url": "b", "type": "text/vtt"},
            ],
        )
        fetched = {"b": self._fake(False, "vtt"), "a": self._fake(True, "text")}
        with patch.object(tm, "fetch_transcript", side_effect=lambda u, f: fetched[u]):
            best = tm.best_publisher_transcript(episode)
        self.assertEqual(best.format, "text")

    @patch("audio_processing.tasks.episode_tasks.process_complete_workflow.delay")
    def test_batch_pending_with_publisher_transcript_resumes_workflow(self, delay):
        episode = self._episode(
            "e",
            [{"url": "a", "type": "application/json"}],
            processing_status=Episode.ProcessingStatus.QUEUED,
            processing_step=Episode.BATCH_PENDING_STEP,
        )
        with patch.object(tm, "fetch_transcript", return_value=self._fake(True)):
            held = tm.resolve_batch_pending([episode])

        self.assertEqual(held, {episode.id})
        episode.refresh_from_db()
        self.assertEqual(episode.transcript_source, "publisher:json")
        self.assertEqual(episode.processing_step, "")
        delay.assert_called_once_with(episode.id)

    @override_config(PUBLISHER_TRANSCRIPT_WAIT_HOURS=12)
    def test_waits_for_podcasts_that_usually_publish(self):
        old = timezone.now() - timedelta(days=3)
        for i in range(4):
            self._episode(
                f"old{i}", [{"url": "x", "type": "text/vtt"}], release_date=old
            )
        new = self._episode("new")
        self.assertTrue(tm.should_wait_for_publisher(new))

        stale = self._episode(
            "stale", release_date=timezone.now() - timedelta(hours=13)
        )
        self.assertFalse(tm.should_wait_for_publisher(stale))

    @override_config(PUBLISHER_TRANSCRIPT_WAIT_HOURS=12)
    def test_no_wait_for_podcasts_that_dont_publish(self):
        self._episode("old", release_date=timezone.now() - timedelta(days=3))
        self.assertFalse(tm.should_wait_for_publisher(self._episode("new")))

    def test_job_marks_unusable_links_and_skips_them_next_time(self):
        episode = self._episode("e", [{"url": "a", "type": "application/json"}])
        with (
            patch.object(Podcast, "refresh_transcript_links", return_value=0),
            patch.object(tm, "fetch_transcript", return_value=None) as fetch,
        ):
            tm.find_publisher_transcripts()
            tm.find_publisher_transcripts()
        self.assertEqual(fetch.call_count, 1)
        episode.refresh_from_db()
        self.assertIsNotNone(episode.publisher_transcript_checked_at)

        episode.set_transcript_links([{"url": "b", "type": "text/vtt"}])
        episode.refresh_from_db()
        self.assertIsNone(episode.publisher_transcript_checked_at)

    def test_feed_processing_records_links(self):
        with patch.object(Podcast, "_download_feed", return_value=FEED):
            self.podcast.process_feed()
        one = Episode.objects.get(podcast=self.podcast, title="One")
        two = Episode.objects.get(podcast=self.podcast, title="Two")
        self.assertEqual(len(one.transcript_links), 3)
        self.assertEqual(two.transcript_links, [])
