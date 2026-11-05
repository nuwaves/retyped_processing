from django import template

from audio_processing.admin.status import status_badge as render_status_badge

register = template.Library()


@register.simple_tag
def status_badge(episode):
    return render_status_badge(episode)


@register.filter
def short_duration(value):
    """Format a timedelta as h:mm:ss or m:ss."""
    if not value:
        return "–"
    total = int(value.total_seconds())
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"
