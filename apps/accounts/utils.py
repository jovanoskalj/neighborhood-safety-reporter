"""Utility functions for managing user notifications."""

from .models import UserNotification


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
