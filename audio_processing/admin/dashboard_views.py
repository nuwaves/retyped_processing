"""
Views for the custom admin pages: dashboard, add-feed flow, processing queue
and per-podcast episode management. Wired up in audio_processing/admin_site.py,
which wraps each one in admin_view (staff login required).
"""

import logging
from datetime import UTC, datetime, timedelta

import feedparser
import requests
from django.conf import settings
from django.contrib import admin, messages
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from audio_processing.admin.forms import (
    FeedUrlForm,
    ImportOptionsForm,
    PodcastSettingsForm,
)
from audio_processing.models import Episode, Podcast
from audio_processing.tasks.podcast_tasks import import_podcast, process_podcast_by_id

logger = logging.getLogger(__name__)

Status = Episode.ProcessingStatus
FEED_PREVIEW_TIMEOUT = 15  # seconds
QUEUE_TABS = (
    ("queued", "Queued"),
    ("running", "Running"),
    ("failed", "Failed"),
    ("done", "Done (24h)"),
)


def _is_partial(request):
    return request.headers.get("X-Partial") == "1"


def _context(request, **extra):
    return {**admin.site.each_context(request), **extra}


def _redirect_back(request, fallback):
    target = request.POST.get("next") or request.GET.get("next")
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(target)
    return redirect(fallback)


def _stalled_cutoff():
    return timezone.now() - timedelta(seconds=settings.CELERY_TASK_TIME_LIMIT)


def _new_unprocessed():
    week_ago = timezone.now() - timedelta(days=7)
    return (
        Episode.objects.filter(
            processing_status=Status.IDLE,
            release_date__gte=week_ago,
            podcast__is_active=True,
        )
        .select_related("podcast")
        .order_by("-release_date")
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------


def dashboard_context():
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    stats = Episode.objects.aggregate(
        total=Count("id"),
        queued=Count("id", filter=Q(processing_status=Status.QUEUED)),
        running=Count("id", filter=Q(processing_status=Status.RUNNING)),
        stalled=Count(
            "id",
            filter=Q(
                processing_status=Status.RUNNING,
                processing_started_at__lt=_stalled_cutoff(),
            ),
        ),
        failed=Count("id", filter=Q(processing_status=Status.FAILED)),
        done_week=Count(
            "id",
            filter=Q(
                processing_status=Status.DONE, processing_completed_at__gte=week_ago
            ),
        ),
    )
    stats["active_podcasts"] = Podcast.objects.filter(is_active=True).count()
    new_unprocessed = _new_unprocessed()
    recent = (
        Episode.objects.filter(processing_status__in=[Status.DONE, Status.FAILED])
        .select_related("podcast")
        .order_by("-updated_at")[:15]
    )
    return {
        "stats": stats,
        "new_unprocessed": new_unprocessed[:25],
        "new_unprocessed_count": new_unprocessed.count(),
        "recent_activity": recent,
    }


# ---------------------------------------------------------------------------
# Add podcast
# ---------------------------------------------------------------------------


def _fetch_feed_preview(url):
    """Download and parse a feed for preview. Returns (feed, error_message)."""
    try:
        response = requests.get(
            url,
            timeout=FEED_PREVIEW_TIMEOUT,
            headers={"User-Agent": "RetypedFeedPreview/1.0"},
        )
        response.raise_for_status()
    except requests.RequestException as e:
        return None, f"Couldn't download the feed: {e}"
    feed = feedparser.parse(response.content)
    if not feed.entries:
        return None, "That URL didn't return any podcast episodes. Is it an RSS feed?"
    return feed, None


def _preview_data(feed):
    info = feed.feed
    image = (info.get("image") or {}).get("href") or (
        info.get("itunes_image") or {}
    ).get("href")
    entries = []
    for entry in feed.entries[:10]:
        published = entry.get("published_parsed")
        entries.append(
            {
                "title": entry.get("title", "Untitled"),
                "published": datetime(*published[:6], tzinfo=UTC)
                if published
                else None,
                "duration": entry.get("itunes_duration"),
            }
        )
    return {
        "title": info.get("title", "Untitled podcast"),
        "author": info.get("author") or info.get("itunes_author"),
        "image": image,
        "episode_count": len(feed.entries),
        "entries": entries,
    }


def add_feed(request):
    title = "Add podcast"
    if request.method != "POST":
        return render(
            request,
            "retyped_admin/add_feed.html",
            _context(request, title=title, form=FeedUrlForm()),
        )

    step = request.POST.get("step", "preview")
    form_class = ImportOptionsForm if step == "create" else FeedUrlForm
    form = form_class(request.POST)
    if not form.is_valid():
        return render(
            request,
            "retyped_admin/add_feed.html",
            _context(
                request,
                title=title,
                form=FeedUrlForm(request.POST),
                existing=getattr(form, "existing", None),
            ),
        )

    url = form.cleaned_data["url"]
    if step == "preview":
        feed, error = _fetch_feed_preview(url)
        if error:
            form.add_error("url", error)
            return render(
                request,
                "retyped_admin/add_feed.html",
                _context(request, title=title, form=form),
            )
        return render(
            request,
            "retyped_admin/add_feed_preview.html",
            _context(
                request,
                title=title,
                preview=_preview_data(feed),
                form=ImportOptionsForm(initial={"url": url}),
            ),
        )

    # step == "create"
    data = form.cleaned_data
    podcast = Podcast.objects.create(
        url=url,
        name=request.POST.get("feed_title") or url,
        is_active=True,
        auto_process=data["auto_process"],
        auto_process_count=data["auto_process_count"],
    )
    import_podcast.delay(podcast.id, process_latest=data["process_latest"])
    messages.success(
        request,
        f"Added “{podcast.name}”. Fetching episodes now"
        + (
            f" and queueing the latest {data['process_latest']} for processing."
            if data["process_latest"]
            else "."
        ),
    )
    return redirect("admin:podcast_episodes", pk=podcast.pk)


# ---------------------------------------------------------------------------
# Podcast episodes
# ---------------------------------------------------------------------------


def podcast_episodes(request, pk):
    podcast = get_object_or_404(Podcast, pk=pk)
    episodes = podcast.episodes.order_by("-release_date", "-id")
    status_filter = request.GET.get("status", "")
    if status_filter in Status.values:
        episodes = episodes.filter(processing_status=status_filter)
    page = Paginator(episodes, 50).get_page(request.GET.get("page"))
    counts = podcast.episodes.aggregate(
        total=Count("id"),
        idle=Count("id", filter=Q(processing_status=Status.IDLE)),
        active=Count(
            "id",
            filter=Q(processing_status__in=[Status.QUEUED, Status.RUNNING]),
        ),
        done=Count("id", filter=Q(processing_status=Status.DONE)),
        failed=Count("id", filter=Q(processing_status=Status.FAILED)),
    )
    context = _context(
        request,
        title=podcast.name,
        podcast=podcast,
        page=page,
        counts=counts,
        status_filter=status_filter,
        status_choices=Status.choices,
        settings_form=PodcastSettingsForm(instance=podcast),
        # Keep refreshing while work is in flight or a new feed hasn't been fetched yet.
        poll=counts["active"] > 0
        or (podcast.is_active and podcast.last_processed is None),
    )
    template = (
        "retyped_admin/partials/podcast_episode_rows.html"
        if _is_partial(request)
        else "retyped_admin/podcast_episodes.html"
    )
    return render(request, template, context)


@require_POST
def podcast_action(request, pk):
    podcast = get_object_or_404(Podcast, pk=pk)
    action = request.POST.get("action")
    back = reverse("admin:podcast_episodes", args=[pk])

    if action == "refresh":
        if not podcast.is_active:
            messages.error(request, "This podcast is inactive. Activate it first.")
        else:
            process_podcast_by_id.delay(podcast.id)
            messages.success(
                request, "Refreshing the feed. New episodes will appear shortly."
            )
    elif action == "settings":
        form = PodcastSettingsForm(request.POST, instance=podcast)
        if form.is_valid():
            form.save()
            messages.success(request, "Settings saved.")
        else:
            messages.error(request, f"Settings not saved: {form.errors.as_text()}")
    elif action == "process_newest":
        try:
            count = max(0, min(int(request.POST.get("count", 0)), 25))
        except ValueError:
            count = 0
        queued = podcast.queue_newest_episodes(count)
        messages.success(request, f"Queued {queued} episode(s) for processing.")
    else:
        messages.error(request, "Unknown action.")
    return _redirect_back(request, back)


# ---------------------------------------------------------------------------
# Processing queue
# ---------------------------------------------------------------------------


def processing_queue(request):
    tab = request.GET.get("tab", "running")
    if tab not in dict(QUEUE_TABS):
        tab = "running"

    episodes = Episode.objects.select_related("podcast")
    if tab == "queued":
        episodes = episodes.filter(processing_status=Status.QUEUED).order_by(
            "processing_queued_at"
        )
    elif tab == "running":
        episodes = episodes.filter(processing_status=Status.RUNNING).order_by(
            "processing_started_at"
        )
    elif tab == "failed":
        episodes = episodes.filter(processing_status=Status.FAILED).order_by(
            "-updated_at"
        )
    else:
        episodes = episodes.filter(
            processing_status=Status.DONE,
            processing_completed_at__gte=timezone.now() - timedelta(hours=24),
        ).order_by("-processing_completed_at")

    counts = Episode.objects.aggregate(
        queued=Count("id", filter=Q(processing_status=Status.QUEUED)),
        running=Count("id", filter=Q(processing_status=Status.RUNNING)),
        failed=Count("id", filter=Q(processing_status=Status.FAILED)),
        done=Count(
            "id",
            filter=Q(
                processing_status=Status.DONE,
                processing_completed_at__gte=timezone.now() - timedelta(hours=24),
            ),
        ),
    )
    page = Paginator(episodes, 50).get_page(request.GET.get("page"))
    context = _context(
        request,
        title="Processing queue",
        tab=tab,
        tabs=[(key, label, counts[key]) for key, label in QUEUE_TABS],
        page=page,
        now=timezone.now(),
    )
    template = (
        "retyped_admin/partials/queue_body.html"
        if _is_partial(request)
        else "retyped_admin/processing_queue.html"
    )
    return render(request, template, context)


@require_POST
def queue_episodes(request):
    """
    Queue (or retry) processing. Accepts any of:
      - episode_ids: one or more episode ids
      - scope=new_unprocessed: everything in the dashboard's "new and unprocessed" list
      - scope=all_failed: every failed episode
    """
    scope = request.POST.get("scope")
    if scope == "new_unprocessed":
        episodes = _new_unprocessed()
    elif scope == "all_failed":
        episodes = Episode.objects.filter(processing_status=Status.FAILED)
    else:
        ids = [i for i in request.POST.getlist("episode_ids") if i.isdigit()]
        episodes = Episode.objects.filter(id__in=ids)

    queued = skipped = 0
    for episode in episodes:
        # force=False still allows re-queueing stalled runs (see Episode.queue_processing)
        if episode.queue_processing():
            queued += 1
        else:
            skipped += 1

    if not queued and not skipped:
        messages.warning(request, "No episodes selected.")
    else:
        message = f"Queued {queued} episode(s) for processing."
        if skipped:
            message += f" Skipped {skipped} already queued or running."
        messages.success(request, message)
    return _redirect_back(request, reverse("admin:processing_queue"))
