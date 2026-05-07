from concurrent.futures import ThreadPoolExecutor
import logging

from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.ai_classifier.classifier import classify_report
from .models import Report

logger = logging.getLogger(__name__)

CLASSIFICATION_TIMEOUT_SECONDS = 2


def _normalize_classification(classification):
    if not isinstance(classification, dict):
        raise ValueError("Classification response must be an object")

    category = str(classification.get("category", "")).strip().lower()
    priority = str(classification.get("priority", "")).strip().lower()
    sector = str(classification.get("sector", "")).strip().lower()

    valid_categories = {choice[0] for choice in Report.CATEGORY_CHOICES}
    valid_priorities = {choice[0] for choice in Report.PRIORITY_CHOICES}
    valid_sectors = {choice[0] for choice in Report.SECTOR_CHOICES}

    if category not in valid_categories:
        raise ValueError(f"Invalid category returned by classifier: {category}")
    if priority not in valid_priorities:
        raise ValueError(f"Invalid priority returned by classifier: {priority}")
    if sector not in valid_sectors:
        raise ValueError(f"Invalid sector returned by classifier: {sector}")

    return {"category": category, "priority": priority, "sector": sector}


@receiver(post_save, sender=Report)
def classify_report_on_create(sender, instance, created, **kwargs):
    if not created:
        return
    if not getattr(settings, "AI_CLASSIFICATION_ENABLED", False):
        return
    if instance.ai_processed or instance.status == "unclassified":
        return

    classification = None
    try:
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(classify_report, instance.description)
            raw_classification = future.result(timeout=CLASSIFICATION_TIMEOUT_SECONDS)
        classification = _normalize_classification(raw_classification)
    except Exception:
        logger.exception("AI classification failed or timed out for report id=%s", instance.pk)

    if classification is not None:
        Report.objects.filter(pk=instance.pk).update(
            category=classification["category"],
            priority=classification["priority"],
            sector=classification["sector"],
            ai_processed=True,
        )
    else:
        Report.objects.filter(pk=instance.pk).update(
            status="unclassified",
            ai_processed=False,
        )
