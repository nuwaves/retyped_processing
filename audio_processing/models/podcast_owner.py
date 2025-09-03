from django.db import models
from django.core.validators import EmailValidator
from django.utils import timezone


class PodcastOwner(models.Model):
    """
    Model to track podcast ownership, contact information, and approval status.
    
    This model manages the relationship between podcasts and their owners,
    including contact details and approval workflow tracking.
    """
    
    # Relationship to Podcast
    podcast = models.OneToOneField(
        'Podcast',
        on_delete=models.CASCADE,
        related_name='owner',
        help_text="The podcast this owner is associated with"
    )
    
    # Contact Information
    email = models.EmailField(
        validators=[EmailValidator()],
        help_text="Contact email address for the podcast owner"
    )
    first_name = models.CharField(
        max_length=100,
        help_text="Owner's first name"
    )
    last_name = models.CharField(
        max_length=100,
        help_text="Owner's last name"
    )
    
    # Approval Status Tracking
    APPROVAL_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]
    
    approval_status = models.CharField(
        max_length=20,
        choices=APPROVAL_STATUS_CHOICES,
        default='pending',
        help_text="Current approval status"
    )
    
    date_approved = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Date when the owner was approved"
    )
    
    date_rejected = models.DateTimeField(
        blank=True,
        null=True,
        help_text="Date when the owner was rejected"
    )
    
    # Additional fields for approval workflow
    approval_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Internal notes about the approval/rejection decision"
    )
    
    approved_by = models.ForeignKey(
        'auth.User',
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name='approved_podcast_owners',
        help_text="Admin user who approved/rejected this owner"
    )
    
    # System timestamps
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this owner record was created"
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        help_text="When this owner record was last updated"
    )

    class Meta:
        verbose_name = "Podcast Owner"
        verbose_name_plural = "Podcast Owners"
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['approval_status']),
            models.Index(fields=['email']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.full_name} - {self.podcast.name if self.podcast else 'No Podcast'}"

    @property
    def full_name(self):
        """Return the owner's full name."""
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_approved(self):
        """Check if the owner is approved."""
        return self.approval_status == 'approved'

    @property
    def is_pending(self):
        """Check if the owner is pending approval."""
        return self.approval_status == 'pending'

    @property
    def is_rejected(self):
        """Check if the owner is rejected."""
        return self.approval_status == 'rejected'

    def approve(self, approved_by=None, notes=None):
        """
        Approve this podcast owner.
        
        Args:
            approved_by (User): The admin user approving this owner
            notes (str): Optional approval notes
        """
        self.approval_status = 'approved'
        self.date_approved = timezone.now()
        self.date_rejected = None  # Clear any previous rejection
        if approved_by:
            self.approved_by = approved_by
        if notes:
            self.approval_notes = notes
        self.save()

    def reject(self, rejected_by=None, notes=None):
        """
        Reject this podcast owner.
        
        Args:
            rejected_by (User): The admin user rejecting this owner
            notes (str): Optional rejection notes
        """
        self.approval_status = 'rejected'
        self.date_rejected = timezone.now()
        self.date_approved = None  # Clear any previous approval
        if rejected_by:
            self.approved_by = rejected_by
        if notes:
            self.approval_notes = notes
        self.save()

    def reset_to_pending(self):
        """Reset the owner status back to pending."""
        self.approval_status = 'pending'
        self.date_approved = None
        self.date_rejected = None
        self.approved_by = None
        self.approval_notes = None
        self.save()

    def clean(self):
        """Validate the model data."""
        from django.core.exceptions import ValidationError
        
        # Ensure approval/rejection dates match the status
        if self.approval_status == 'approved' and not self.date_approved:
            self.date_approved = timezone.now()
        elif self.approval_status == 'rejected' and not self.date_rejected:
            self.date_rejected = timezone.now()
        elif self.approval_status == 'pending':
            if self.date_approved or self.date_rejected:
                # If status is pending, clear any approval/rejection dates
                self.date_approved = None
                self.date_rejected = None

    def save(self, *args, **kwargs):
        """Override save to run validation."""
        self.clean()
        super().save(*args, **kwargs)