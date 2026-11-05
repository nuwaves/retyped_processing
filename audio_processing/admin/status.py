"""Shared rendering of an episode's processing status for admin pages."""

from django.utils.html import format_html

# (label, background, text colour) per status; inline so it renders on stock admin pages too.
_BADGES = {
    "idle": ("Not processed", "#e5e7eb", "#374151"),
    "queued": ("Queued", "#dbeafe", "#1e40af"),
    "running": ("Running", "#fef3c7", "#92400e"),
    "done": ("Done", "#dcfce7", "#166534"),
    "failed": ("Failed", "#fee2e2", "#991b1b"),
    "stalled": ("Stalled", "#fde68a", "#7c2d12"),
}


def status_key(episode):
    return "stalled" if episode.is_stalled else episode.processing_status


def status_badge(episode):
    label, bg, fg = _BADGES.get(status_key(episode), _BADGES["idle"])
    step = ""
    if episode.processing_status in ("running", "failed") and episode.processing_step:
        step = f" · {episode.processing_step}"
    return format_html(
        '<span class="rt-badge" style="display:inline-block;padding:2px 8px;'
        "border-radius:999px;font-size:11px;font-weight:600;white-space:nowrap;"
        'background:{};color:{}">{}{}</span>',
        bg,
        fg,
        label,
        step,
    )
