"""Utility functions for managing user notifications."""

from apps.reports.models import ReportCategory, Sector

from .models import UserNotification, UserProfile


def create_user_notification(user, notification_type, title, message, report=None):
    """
    Create a user notification.
    
    Args:
        user: The user to notify
        notification_type: Type of notification (status_change, report_submitted, etc.)
        title: Notification title
        message: Notification message
        report: Optional related report object
    
    Returns:
        UserNotification object
    """
    return UserNotification.objects.create(
        user=user,
        type=notification_type,
        title=title,
        message=message,
        report=report
    )


def get_unread_count(user):
    """Get the count of unread notifications for a user."""
    return UserNotification.objects.filter(user=user, is_read=False).count()


def get_recent_notifications(user, limit=5):
    """Get recent notifications for a user."""
    return UserNotification.objects.filter(user=user).order_by('-created_at')[:limit]


def mark_as_read(user, notification_id=None):
    """
    Mark notifications as read.
    
    Args:
        user: The user whose notifications to mark
        notification_id: Specific notification ID to mark, or None to mark all
    """
    queryset = UserNotification.objects.filter(user=user, is_read=False)
    if notification_id:
        queryset = queryset.filter(id=notification_id)
    return queryset.update(is_read=True)


def notify_report_resolved(report):
    """
    Create notification when a report is resolved.
    
    Args:
        report: The resolved report
    """
    if report.citizen:
        create_user_notification(
            user=report.citizen,
            notification_type='status_change',
            title=f'Пријавата #{report.id} е решена',
            message=f'Вашата пријава е успешно решена. Ви благодариме за пријавување!',
            report=report
        )


def notify_report_status_changed(report, old_status, new_status):
    """Create an in-app notification for the citizen when a report status changes."""
    if not report.citizen or old_status == new_status:
        return None

    status_labels = dict(report.STATUS_CHOICES)
    old_status_label = status_labels.get(old_status, old_status)
    new_status_label = status_labels.get(new_status, new_status)

    return create_user_notification(
        user=report.citizen,
        notification_type="status_change",
        title=f"Статусот на пријава #{report.id} е променет",
        message=f"Статусот е променет од {old_status_label} во {new_status_label}.",
        report=report,
    )


def notify_report_classified(report, classified_by=None):
    """Notify the citizen and active officers/workers assigned to the report's sector."""
    officer_profiles = UserProfile.objects.select_related("user").filter(
        role="officer",
        sector=report.sector,
        user__is_active=True,
    )

    sector_labels = {
        **dict(report.SECTOR_CHOICES),
        **dict(Sector.objects.values_list("key", "name")),
    }
    category_labels = {
        **dict(report.CATEGORY_CHOICES),
        **dict(ReportCategory.objects.values_list("key", "name")),
    }
    classifier_name = classified_by.get_full_name() or classified_by.username if classified_by else "Администратор"
    notifications = []
    category_label = category_labels.get(report.category, report.category)
    sector_label = sector_labels.get(report.sector, report.sector)

    if report.citizen:
        notifications.append(
            create_user_notification(
                user=report.citizen,
                notification_type="system",
                title=f"Пријава #{report.id} е класифицирана",
                message=f"Вашата пријава е класифицирана како {category_label}.",
                report=report,
            )
        )

    for profile in officer_profiles:
        notifications.append(
            create_user_notification(
                user=profile.user,
                notification_type="report_assigned",
                title=f"Пријава #{report.id} е класифицирана",
                message=(
                    f"{classifier_name} ја класифицираше пријавата како "
                    f"{category_label} "
                    f"и ја додели на сектор {sector_label}."
                ),
                report=report,
            )
        )

    return notifications


def notify_report_reassigned(report, old_sector, reassigned_by=None):
    """Notify active officers/workers in the destination sector after reassignment."""
    officer_profiles = UserProfile.objects.select_related("user").filter(
        role="officer",
        sector=report.sector,
        user__is_active=True,
    )
    if report.municipality:
        officer_profiles = officer_profiles.filter(municipality__in=["", report.municipality])

    sector_labels = {
        **dict(report.SECTOR_CHOICES),
        **dict(Sector.objects.values_list("key", "name")),
    }
    actor_name = reassigned_by.get_full_name() or reassigned_by.username if reassigned_by else "Работник"
    old_sector_label = sector_labels.get(old_sector, old_sector)
    new_sector_label = sector_labels.get(report.sector, report.sector)
    notifications = []

    for profile in officer_profiles:
        notifications.append(
            create_user_notification(
                user=profile.user,
                notification_type="report_assigned",
                title=f"Пријава #{report.id} е пренасочена",
                message=(
                    f"{actor_name} ја пренасочи пријавата од сектор "
                    f"{old_sector_label} кон {new_sector_label}."
                ),
                report=report,
            )
        )

    return notifications


def cleanup_old_notifications(days_old=90):
    """
    Delete notifications older than specified days.
    
    Args:
        days_old: Number of days to keep notifications
    """
    from django.utils import timezone
    from datetime import timedelta
    
    cutoff_date = timezone.now() - timedelta(days=days_old)
    deleted_count = UserNotification.objects.filter(
        created_at__lt=cutoff_date,
        is_read=True
    ).delete()[0]
    
    return deleted_count
