"""Email notification helpers for report lifecycle events."""
from django.conf import settings
from django.core.mail import send_mail


def send_status_change_email(report) -> None:
    """Notify a report's citizen that the report's status has changed."""
    email = getattr(report.citizen, "email", "") or ""
    if not email:
        return
    subject = f"Вашата пријава #{report.pk} е ажурирана"
    message = (
        f"Здраво {report.citizen.username},\n\n"
        f"Статусот на вашата пријава е променет на: {report.get_status_display()}.\n"
        "Ви благодариме за вашата соработка."
    )
    send_mail(
        subject=subject,
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=True,
    )
