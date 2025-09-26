from django.db import models
from django.core.validators import MinLengthValidator
import logging

logger = logging.getLogger(__name__)


class Quote(models.Model):
    """
    Model to store memorable quotes from podcast episodes.
    
    This model captures specific quotes or segments from episodes,
    including the speaker and the exact text content.
    """
    
    # Relationship to Episode
    episode = models.ForeignKey(
        'Episode',
        on_delete=models.CASCADE,
        related_name='quotes',
        help_text="The episode this quote is from"
    )
    
    # Quote content
    text = models.TextField(
        validators=[MinLengthValidator(10)],
        help_text="The actual quote text content"
    )
    
    speaker = models.CharField(
        max_length=2000,
        blank=True,
        null=True,
        help_text="Name or identifier of the person who said this quote"
    )
    
    # Metadata
    timestamp = models.DurationField(
        blank=True,
        null=True,
        help_text="Timestamp in the episode where this quote appears (e.g., 00:15:30)"
    )
    
    # System fields
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this quote was added"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this quote was last updated"
    )
    
    class Meta:
        verbose_name = "Quote"
        verbose_name_plural = "Quotes"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['episode']),
            models.Index(fields=['speaker']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        """Return a truncated version of the quote with speaker info."""
        text_preview = self.text[:100] + "..." if len(self.text) > 100 else self.text
        if self.speaker:
            return f'"{text_preview}" - {self.speaker}'
        else:
            return f'"{text_preview}"'

    def get_shareable_text(self):
        """
        Generate a formatted text suitable for sharing on social media.
        """
        if self.speaker:
            return f'"{self.text}"\n\n- {self.speaker}\n{self.episode_title} | {self.podcast_name}'
        else:
            return f'"{self.text}"\n\n{self.episode_title} | {self.podcast_name}'