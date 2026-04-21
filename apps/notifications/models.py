"""Persistent log of email-notification attempts (task T-22)."""
from django.db import models


class Notification(models.Model):
    """One row per email send attempt — recorded by ``senders.py``."""

    TYPE_CHOICES = [
        ("status_change", "Промена на статус"),
        ("report_submitted", "Поднесена пријава"),
        ("bulk", "Масовно известување"),
    ]

    STATUS_CHOICES = [
        ("sent", "Испратено"),
        ("failed", "Неуспешно"),
        ("pending", "Во чекање"),
    ]

    time = models.DateTimeField(auto_now_add=True)
    type = models.CharField(max_length=50, choices=TYPE_CHOICES)
    subject = models.CharField(max_length=255, blank=True, default="")
    message = models.TextField()
    recipient = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")

    class Meta:
        ordering = ["-time"]

    def __str__(self) -> str:
        return f"{self.type} → {self.recipient} [{self.status}]"
