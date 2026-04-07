from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone


class UserProfile(models.Model):
    """Additional user metadata: role, sector, and phone."""

    ROLE_CHOICES = [
        ('citizen', 'Citizen'),
        ('officer', 'Officer'),
        ('admin', 'Administrator')
    ]

    SECTOR_CHOICES = [
        ('infrastructure', 'Infrastructure'),
        ('utilities', 'Utilities'),
        ('safety', 'Safety'),
        ('health', 'Health'),
        ('admin', 'Administration')
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='citizen')
    sector = models.CharField(max_length=50, choices=SECTOR_CHOICES, blank=True)  # only for officers
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"{self.user.username} - {self.role}"


class AuditLog(models.Model):
    """Tracks relevant user/admin actions for accountability."""

    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=255)
    target_model = models.CharField(max_length=100)
    target_id = models.IntegerField(null=True)
    timestamp = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict)

    def __str__(self) -> str:
        return f"{self.action} by {self.user_id} @ {self.timestamp.isoformat()}"


class EmailVerificationCode(models.Model):
    """One-time 6-digit email verification code for inactive users."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="email_verification_code")
    code = models.CharField(max_length=6)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def __str__(self) -> str:
        return f"Verification code for {self.user_id} (expires {self.expires_at.isoformat()})"