from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.ai_classifier.classifier import classify_report

from .models import Report


@receiver(post_save, sender=Report)
def classify_report_on_create(sender, instance, created, **kwargs):
    if not created:
        return

    try:
        classification = classify_report(instance.description)
    except Exception:
        classification = {
            "category": "other",
            "priority": "normal",
            "sector": "admin",
        }

    Report.objects.filter(pk=instance.pk).update(
        category=classification.get("category", "other") or "other",
        priority=classification.get("priority", "normal") or "normal",
        sector=classification.get("sector", "admin") or "admin",
    )
