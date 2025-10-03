from django.db import models
from django.contrib.auth.models import User
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType


class Follow(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="follows")
    content_type = models.ForeignKey(
        ContentType,
        on_delete=models.CASCADE,
        limit_choices_to={"model__in": ("tag", "podcast")},
    )
    object_id = models.BigIntegerField()
    followed_entity = GenericForeignKey("content_type", "object_id")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Follow"
        verbose_name_plural = "Follows"
        ordering = ["-created_at"]
        unique_together = ["content_type", "object_id", "user"]
        indexes = [
            models.Index(fields=["content_type", "object_id"]),
        ]

    def __str__(self):
        return f"{self.user.email} | {self.content_type} - {self.object_id}"