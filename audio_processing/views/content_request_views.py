from django.contrib.auth.models import User
from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from ..models import ContentRequest, Episode


def episode_content_status(episode):
    """Where an episode's transcript and summary stand, for the request panel."""
    if Episode.objects.filter(pk=episode.pk).filter(Episode.has_content_q()).exists():
        return "available"
    if (
        episode.processing_status
        in (
            Episode.ProcessingStatus.QUEUED,
            Episode.ProcessingStatus.RUNNING,
        )
        and not episode.is_stalled
    ):
        return "processing"
    if episode.processing_status == Episode.ProcessingStatus.FAILED:
        return "failed"
    return "not_requested"


class EpisodeContentRequestView(APIView):
    """
    GET  /api/v1/episodes/<slug>/content-request/
        The episode's status, whether the signed-in user has asked for it, and
        their remaining allowance. Works signed out (no allowance then).
    POST /api/v1/episodes/<slug>/content-request/
        Ask for a transcript and summary. Signed-in only. Queues the processing
        workflow and uses one request from the user's daily/monthly allowance.
        Asking again for an episode you already asked for, or one that is
        already being processed, uses nothing.
    """

    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def _payload(self, request, episode):
        user = request.user if request.user.is_authenticated else None
        return {
            "status": episode_content_status(episode),
            "requested": bool(
                user
                and ContentRequest.objects.filter(user=user, episode=episode).exists()
            ),
            "quota": ContentRequest.quota_for(user) if user else None,
        }

    def get(self, request, slug):
        episode = get_object_or_404(Episode, slug=slug)
        return Response(self._payload(request, episode))

    def post(self, request, slug):
        episode = get_object_or_404(Episode, slug=slug)
        user = request.user

        with transaction.atomic():
            # Serialize a user's requests so two quick clicks can't both pass
            # the allowance check.
            User.objects.select_for_update().get(pk=user.pk)
            episode.refresh_from_db()
            current = episode_content_status(episode)

            if current in ("available", "processing"):
                return Response(self._payload(request, episode))

            already_requested = ContentRequest.objects.filter(
                user=user, episode=episode
            ).exists()
            if not already_requested:
                quota = ContentRequest.quota_for(user)
                if quota["remaining"] is not None and quota["remaining"] <= 0:
                    return Response(
                        {
                            "detail": "You've used all your requests for now.",
                            "code": "quota_exceeded",
                            "quota": quota,
                        },
                        status=status.HTTP_429_TOO_MANY_REQUESTS,
                    )
                ContentRequest.objects.create(user=user, episode=episode)

            # Transcribe right away rather than waiting for the next batch: the
            # allowance keeps the cost of realtime transcription bounded.
            transaction.on_commit(lambda: episode.queue_processing(realtime=True))

        episode.refresh_from_db()
        payload = self._payload(request, episode)
        payload["status"] = "processing"
        return Response(payload, status=status.HTTP_201_CREATED)
