from django.contrib import admin

from audio_processing.models import Topic


def enable_topics(modeladmin, request, queryset):
    queryset.update(is_enabled=True)


enable_topics.short_description = "Enable selected topics"


def disable_topics(modeladmin, request, queryset):
    queryset.update(is_enabled=False)


disable_topics.short_description = "Disable selected topics"


@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_enabled", "created_at", "updated_at")
    list_filter = ("is_enabled",)
    list_editable = ("is_enabled",)
    search_fields = ("name", "slug", "description")
    readonly_fields = ("created_at", "updated_at")
    prepopulated_fields = {"slug": ("name",)}
    actions = [enable_topics, disable_topics]
    fieldsets = (
        ("Basic Information", {"fields": ("name", "slug", "description", "top_words")}),
        ("Visibility", {"fields": ("is_enabled",)}),
        (
            "Timestamps",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )
