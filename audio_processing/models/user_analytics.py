from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import logging

logger = logging.getLogger(__name__)


class UserAnalytics(models.Model):
    """
    Analytics model to track user interactions with podcasts or episodes.
    Each record represents analytics for one user with one entity (podcast OR episode).
    """
    
    # User relationship
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='analytics',
        help_text="User who performed the action"
    )
    
    # Entity relationships (one of these will be set)
    podcast = models.ForeignKey(
        'Podcast',
        on_delete=models.CASCADE,
        related_name='user_analytics',
        blank=True,
        null=True,
        help_text="Podcast this analytics record refers to"
    )
    episode = models.ForeignKey(
        'Episode',
        on_delete=models.CASCADE,
        related_name='user_analytics',
        blank=True,
        null=True,
        help_text="Episode this analytics record refers to"
    )
    views = models.IntegerField(
        default=0,
        help_text="Number of views for this analytics record"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


    class Meta:
        verbose_name = "User Analytics"
        verbose_name_plural = "User Analytics"
        ordering = ['-updated_at']
        indexes = [
            models.Index(fields=['user']),
            models.Index(fields=['podcast']),
            models.Index(fields=['episode']),
        ]
        
        # Ensure we have analytics for either podcast OR episode, not both
        constraints = [
            models.CheckConstraint(
                check=models.Q(podcast__isnull=False) | models.Q(episode__isnull=False),
                name='user_analytics_has_entity'
            ),
            models.CheckConstraint(
                check=~(models.Q(podcast__isnull=False) & models.Q(episode__isnull=False)),
                name='user_analytics_single_entity'
            ),
        ]

    def __str__(self):
        entity_name = ""
        if self.podcast:
            entity_name = f"Podcast: {self.podcast.name}"
        elif self.episode:
            entity_name = f"Episode: {self.episode.title}"
        
        return f"{self.user.username} - {entity_name}"

    def clean(self):
        """Validate that exactly one of podcast or episode is set."""
        super().clean()
        
        # Check that exactly one entity is set
        if not self.podcast and not self.episode:
            raise ValidationError("Either podcast or episode must be specified.")
        
        if self.podcast and self.episode:
            raise ValidationError("Cannot specify both podcast and episode.")

    def save(self, *args, **kwargs):
        """Override save to run validation."""
        self.full_clean()
        super().save(*args, **kwargs)

    @property
    def entity(self):
        """Return the associated entity (podcast or episode)."""
        return self.podcast or self.episode

    @property
    def entity_type(self):
        """Return the type of entity ('podcast' or 'episode')."""
        if self.podcast:
            return 'podcast'
        elif self.episode:
            return 'episode'
        return None

    def get_entity_display_name(self):
        """Get display name of the associated entity."""
        if self.podcast:
            return self.podcast.name
        elif self.episode:
            return self.episode.title
        return "Unknown"