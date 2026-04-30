from concurrent.futures import ThreadPoolExecutor

from django.db import transaction
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from apps.ai_classifier.classifier import classify_report

from .models import Report


_EXECUTOR = ThreadPoolExecutor(max_workers=2)


def _classify_and_update(report_id: int, description: str) -> None:
    result = classify_report(description)
    Report.objects.filter(pk=report_id).update(
        category=result.get("category", "other"),
        priority=result.get("priority", "normal"),
        sector=result.get("sector", "admin"),
        status=result.get("status", "unclassified"),
        ai_processed=True,
        status_changed_at=timezone.now(),
    )


@receiver(post_save, sender=Report)
def run_ai_pipeline_on_create(sender, instance: Report, created: bool, **kwargs) -> None:
    """Async AI pipeline fallback for reports created without direct classification."""
    if not created or instance.ai_processed:
        return

    transaction.on_commit(lambda: _EXECUTOR.submit(_classify_and_update, instance.pk, instance.description))
