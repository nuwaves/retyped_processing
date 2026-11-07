from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class ContentRequest(models.Model):
    """
    A signed-in user asking us to transcribe and summarize an episode that has
    neither yet. Each request queues the processing workflow and counts against
    the user's daily and monthly allowance (see ContentRequest.quota_for).
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="content_requests"
    )
    episode = models.ForeignKey(
        "Episode", on_delete=models.CASCADE, related_name="content_requests"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Content request"
        verbose_name_plural = "Content requests"
        ordering = ["-created_at"]
        unique_together = ["user", "episode"]
        indexes = [
            models.Index(
                fields=["user", "created_at"], name="content_req_user_created_idx"
            )
        ]

    def __str__(self):
        return f"{self.user} | {self.episode}"

    @staticmethod
    def is_unlimited(user):
        """
        Users with no request limit. There is no paid plan yet, so this is
        staff only; switch it to the Pro plan check when billing exists.
        """
        return bool(user and user.is_staff)

    @classmethod
    def quota_for(cls, user):
        """
        The user's request allowance. Days and months are calendar periods in
        the site's time zone, so the daily request comes back at midnight and
        the monthly ones on the 1st.
        """
        from constance import config

        unlimited = cls.is_unlimited(user)
        now = timezone.localtime()
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        mine = cls.objects.filter(user=user)
        used_today = mine.filter(created_at__gte=day_start).count()
        used_this_month = mine.filter(created_at__gte=month_start).count()
        daily_limit = config.CONTENT_REQUESTS_PER_DAY
        monthly_limit = config.CONTENT_REQUESTS_PER_MONTH

        if unlimited:
            remaining = None
            resets_at = None
        else:
            remaining = max(
                0,
                min(daily_limit - used_today, monthly_limit - used_this_month),
            )
            if used_this_month >= monthly_limit:
                next_month = (month_start + timezone.timedelta(days=32)).replace(day=1)
                resets_at = next_month
            elif used_today >= daily_limit:
                resets_at = day_start + timezone.timedelta(days=1)
            else:
                resets_at = None

        return {
            "plan": "pro" if unlimited else "free",
            "daily_limit": None if unlimited else daily_limit,
            "monthly_limit": None if unlimited else monthly_limit,
            "used_today": used_today,
            "used_this_month": used_this_month,
            "remaining": remaining,
            "resets_at": resets_at.isoformat() if resets_at else None,
        }
