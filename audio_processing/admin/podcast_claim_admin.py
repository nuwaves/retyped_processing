"""
Staff review of podcast ownership claims.

Claims only reach APPROVED here: verify() (the emailed owner link) moves a
claim to IN_REVIEW at most. The approve/reject actions need the
change_podcastclaim permission, and the status field is read-only on the form
so approval always goes through an action and is logged.
"""

from django.contrib import admin, messages

from audio_processing.models import ClaimVerification, PodcastClaim


class ClaimVerificationInline(admin.TabularInline):
    model = ClaimVerification
    extra = 0
    can_delete = False
    fields = ("is_verified", "created_at", "updated_at")
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(PodcastClaim)
class PodcastClaimAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "podcast",
        "user",
        "status",
        "owner_email_confirmed",
        "created_at",
    )
    list_filter = ("status", "created_at")
    list_select_related = ("podcast", "user")
    search_fields = ("podcast__name", "user__username", "user__email")
    readonly_fields = ("podcast", "user", "status", "created_at", "updated_at")
    inlines = (ClaimVerificationInline,)
    actions = ("approve_claims", "reject_claims")

    @admin.display(boolean=True, description="Owner email confirmed")
    def owner_email_confirmed(self, obj):
        return obj.claim_verification.filter(is_verified=True).exists()

    def has_add_permission(self, request):
        # Claims are created by users through the API, not by staff.
        return False

    def _set_status(self, request, queryset, status, verb):
        if not request.user.is_staff:
            self.message_user(request, "Staff only.", level=messages.ERROR)
            return
        changed = 0
        for claim in queryset.exclude(status=status):
            claim.status = status
            claim.save(update_fields=["status", "updated_at"])
            self.log_change(request, claim, f"{verb} claim (status={status})")
            changed += 1
        self.message_user(request, f"{verb} {changed} claim(s).")

    @admin.action(description="Approve selected claims", permissions=["change"])
    def approve_claims(self, request, queryset):
        self._set_status(
            request, queryset, PodcastClaim.ClaimStatus.APPROVED, "Approved"
        )

    @admin.action(description="Reject selected claims", permissions=["change"])
    def reject_claims(self, request, queryset):
        self._set_status(
            request, queryset, PodcastClaim.ClaimStatus.REJECTED, "Rejected"
        )
