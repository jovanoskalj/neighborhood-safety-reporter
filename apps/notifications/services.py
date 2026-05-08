import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from apps.reports.models import Report

logger = logging.getLogger(__name__)


def _send_html_email(*, subject: str, to_email: str, template_name: str, context: dict) -> bool:
    if not to_email:
        return False

    try:
        html_body = render_to_string(template_name, context)
        text_body = strip_tags(html_body)
        message = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL or None,
            to=[to_email],
        )
        message.attach_alternative(html_body, "text/html")
        message.send(fail_silently=False)
        return True
    except Exception:
        logger.exception("Failed to send email: %s", subject)
        return False


def send_report_created_email(report: Report) -> bool:
    user = report.citizen
    subject = f"Потврда за пријава #{report.id}"
    return _send_html_email(
        subject=subject,
        to_email=user.email,
        template_name="emails/report_created.html",
        context={
            "user": user,
            "report": report,
        },
    )


def send_report_status_changed_email(report: Report, old_status: str, new_status: str) -> bool:
    user = report.citizen
    status_labels = dict(Report.STATUS_CHOICES)
    subject = f"Промена на статус за пријава #{report.id}"
    return _send_html_email(
        subject=subject,
        to_email=user.email,
        template_name="emails/report_status_changed.html",
        context={
            "user": user,
            "report": report,
            "old_status": old_status,
            "new_status": new_status,
            "old_status_label": status_labels.get(old_status, old_status),
            "new_status_label": status_labels.get(new_status, new_status),
        },
    )
