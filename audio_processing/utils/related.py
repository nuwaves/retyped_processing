"""
Related-episode recommendations for the episode page sidebar.

Episodes are scored by what they share with the source episode:
  - entities (people, companies, products), each weighted by rarity, so two
    episodes that both mention a niche guest score higher than two that both
    mention a household name;
  - topics and tags, at fixed weights;
  - a small recency bonus as a tie-breaker.

Only episodes with a summary or transcript are recommended, so the sidebar
never links to thin pages that are kept out of the index.
"""

import math
from collections import defaultdict

from django.db.models import Count
from django.utils import timezone

from audio_processing.models import Episode

ENTITY_TYPE_ORDER = ("PERSON", "ORGANIZATION", "PRODUCT")

# Entities mentioned in more episodes than this are too generic to say two
# episodes are related, and fetching all their episodes would be expensive.
MAX_ENTITY_EPISODES = 500
TOPIC_WEIGHT = 1.5
TAG_WEIGHT = 0.5
RECENCY_WEIGHT = 0.5
RECENCY_HALF_LIFE_DAYS = 180
# Candidate pool sizes per signal, before scoring.
ENTITY_POOL = 300
TOPIC_POOL = 100
TAG_POOL = 100
MAX_PER_SHOW = 2


def related_episodes(episode, limit=5):
    """Return up to `limit` recommended episodes for `episode`, best first."""
    entity_through = Episode.entities.through
    topic_through = Episode.topics.through
    tag_through = Episode.tags.through

    entity_ids = list(
        entity_through.objects.filter(episode_id=episode.id).values_list(
            "entity_id", flat=True
        )
    )
    topic_ids = list(
        episode.topics.filter(is_enabled=True).values_list("id", flat=True)
    )
    tag_ids = list(episode.tags.values_list("id", flat=True))

    scores = defaultdict(float)

    # Entities: score each candidate by the summed rarity of shared entities.
    if entity_ids:
        doc_freq = dict(
            entity_through.objects.filter(entity_id__in=entity_ids)
            .values("entity_id")
            .annotate(n=Count("episode_id"))
            .values_list("entity_id", "n")
        )
        specific = [eid for eid, n in doc_freq.items() if 1 < n <= MAX_ENTITY_EPISODES]
        pairs = (
            entity_through.objects.filter(entity_id__in=specific)
            .exclude(episode_id=episode.id)
            .values_list("episode_id", "entity_id")
        )
        entity_scores = defaultdict(float)
        for episode_id, entity_id in pairs:
            entity_scores[episode_id] += 1 / math.log(1 + doc_freq[entity_id])
        for episode_id, score in sorted(
            entity_scores.items(), key=lambda item: item[1], reverse=True
        )[:ENTITY_POOL]:
            scores[episode_id] += score

    # Topics and tags: the newest episodes sharing them join the pool, and every
    # pooled episode gets credit for each one it shares.
    for through, relation, field, ids, weight, pool in (
        (topic_through, "topics", "topic_id", topic_ids, TOPIC_WEIGHT, TOPIC_POOL),
        (tag_through, "tags", "tag_id", tag_ids, TAG_WEIGHT, TAG_POOL),
    ):
        if not ids:
            continue
        recent = (
            Episode.objects.filter(**{f"{relation}__in": ids})
            .filter(Episode.has_content_q())
            .exclude(id=episode.id)
            .order_by("-release_date")
            .values_list("id", flat=True)
            .distinct()[:pool]
        )
        candidate_ids = set(scores) | set(recent)
        shared = (
            through.objects.filter(
                episode_id__in=candidate_ids, **{f"{field}__in": ids}
            )
            .values("episode_id")
            .annotate(n=Count(field))
            .values_list("episode_id", "n")
        )
        for episode_id, n in shared:
            scores[episode_id] += weight * n

    results = []
    if scores:
        candidates = (
            Episode.objects.filter(id__in=scores.keys())
            .filter(Episode.has_content_q())
            .select_related("podcast")
            .only(
                "id",
                "slug",
                "title",
                "release_date",
                "duration",
                "image_url",
                "podcast__id",
                "podcast__slug",
                "podcast__name",
                "podcast__image_url",
            )
        )
        now = timezone.now()
        ranked = sorted(
            candidates,
            key=lambda ep: scores[ep.id] + _recency_bonus(ep, now),
            reverse=True,
        )
        per_show = defaultdict(int)
        for candidate in ranked:
            if per_show[candidate.podcast_id] >= MAX_PER_SHOW:
                continue
            per_show[candidate.podcast_id] += 1
            results.append(candidate)
            if len(results) >= limit:
                break

    # Not enough related episodes (e.g. a new episode with no entities yet):
    # fill with the show's latest episodes.
    if len(results) < limit and episode.podcast_id:
        seen = {ep.id for ep in results} | {episode.id}
        results.extend(
            Episode.objects.filter(podcast_id=episode.podcast_id)
            .filter(Episode.has_content_q())
            .exclude(id__in=seen)
            .select_related("podcast")
            .order_by("-release_date")[: limit - len(results)]
        )

    return results


def episode_entities(episode, limit=8):
    """The episode's entities, people first, then organizations, then products."""
    entities = list(episode.entities.all().order_by("name")[:100])
    entities.sort(
        key=lambda entity: (
            ENTITY_TYPE_ORDER.index(entity.type)
            if entity.type in ENTITY_TYPE_ORDER
            else len(ENTITY_TYPE_ORDER)
        )
    )
    return entities[:limit]


def _recency_bonus(episode, now):
    if not episode.release_date:
        return 0.0
    age_days = max((now - episode.release_date).days, 0)
    return RECENCY_WEIGHT * 0.5 ** (age_days / RECENCY_HALF_LIFE_DAYS)
