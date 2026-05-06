"""Email notification helpers."""
import logging

from django.conf import settings
from django.core.mail import send_mail

from .models import Notification

logger = logging.getLogger(__name__)


def _send_and_record(*, type, subject, message, recipient):
    """Send an email and record the attempt as a ``Notification`` row."""
    notification = Notification.objects.create(
        type=type,
        subject=subject,
        message=message,
        recipient=recipient,
        status="pending",
    )
    try:
        send_mail(
            subject=subject,
            message=message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[recipient],
            fail_silently=False,
        )
        notification.status = "sent"
    except Exception:
        logger.exception("Notification %s send failed", notification.pk)
        notification.status = "failed"
    notification.save(update_fields=["status"])
    return notification


def send_status_change_email(report):
    """Notify a report's citizen that the report's status has changed."""
    email = getattr(report.citizen, "email", "") or ""
    if not email:
        return None
    subject = f"Вашата пријава #{report.pk} е ажурирана"
    message = (
        f"Здраво {report.citizen.username},\n\n"
        f"Статусот на вашата пријава е променет на: {report.get_status_display()}.\n"
        "Ви благодариме за вашата соработка."
    )
    return _send_and_record(
        type="status_change",
        subject=subject,
        message=message,
        recipient=email,
    )


def retry_notification(notification):
    """Re-send a previously-failed notification and update its status."""
    if notification.status == "sent":
        return notification
    try:
        send_mail(
            subject=notification.subject,
            message=notification.message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[notification.recipient],
            fail_silently=False,
        )
        notification.status = "sent"
    except Exception:
        logger.exception("Notification %s retry failed", notification.pk)
        notification.status = "failed"
    notification.save(update_fields=["status"])
    return notification


def send_bulk_resolved_email(report, subject=None, message=None):
    """Send a 'resolved' bulk notification for a single report (used by management command)."""
    email = getattr(report.citizen, "email", "") or ""
    if not email:
        return None

    subject = subject or f"Вашата пријава #{report.pk} е решена"
    default_message = (
        f"Здраво {report.citizen.username},\n\n"
        f"Со задоволство ве информираме дека вашата пријава #{report.pk} "
        f"е успешно решена.\n\n"
        f"Опис: {report.description[:200]}\n"
        f"Општина: {report.get_municipality_display()}\n"
        f"Сектор: {report.get_sector_display()}\n\n"
        "Ви благодариме за вашата соработка.\n"
        "Тим за безбедност на населба"
    )
    message = message or default_message
    return _send_and_record(
        type="bulk",
        subject=subject,
        message=message,
        recipient=email,
    )
