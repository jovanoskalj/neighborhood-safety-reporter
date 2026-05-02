"""Signal handlers for account lifecycle and role groups."""

from django.contrib.auth.models import Group, User
from django.db.models.signals import post_migrate, post_save, pre_save
from django.dispatch import receiver

from .models import UserProfile, UserNotification
from apps.reports.models import Report

ROLE_GROUPS = {
    "citizen": ["citizen", "citizens"],
    "officer": ["officer", "officers"],
    "admin": ["admin", "administrators"],
}


@receiver(post_migrate)
def create_default_groups(sender, **kwargs) -> None:
    """Create role groups required by the project after migrations."""
    for aliases in ROLE_GROUPS.values():
        for group_name in aliases:
            Group.objects.get_or_create(name=group_name)


@receiver(post_save, sender=User)
def ensure_user_profile(sender, instance: User, created: bool, **kwargs) -> None:
    """Ensure every user always has a related profile row."""
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=UserProfile)
def sync_groups_with_profile_role(sender, instance: UserProfile, **kwargs) -> None:
    """Keep user groups aligned with profile role changes from admin panel."""
    user = instance.user
    managed_groups = [name for aliases in ROLE_GROUPS.values() for name in aliases]
    user.groups.remove(*Group.objects.filter(name__in=managed_groups))

    for group_name in ROLE_GROUPS.get(instance.role, []):
        group, _ = Group.objects.get_or_create(name=group_name)
        user.groups.add(group)


# User notification signal handlers
def create_notification(user, notification_type, title, message, report=None):
    """Helper function to create a user notification."""
    return UserNotification.objects.create(
        user=user,
        type=notification_type,
        title=title,
        message=message,
        report=report
    )


@receiver(pre_save, sender=Report)
def track_original_status(sender, instance, **kwargs):
    """Store original status before save to detect changes."""
    if not instance._state.adding:
        try:
            instance._original_status = Report.objects.get(pk=instance.pk).status
        except Report.DoesNotExist:
            instance._original_status = None
    else:
        instance._original_status = None


@receiver(post_save, sender=Report)
def report_status_change_notification(sender, instance, created, **kwargs):
    """Create notification when report status changes or new report is submitted."""
    if created:
        # New report submitted - notify officers in the relevant sector
        from apps.accounts.models import UserProfile
        officer_profiles = UserProfile.objects.filter(sector=instance.sector, role='officer')
        for profile in officer_profiles:
            create_notification(
                user=profile.user,
                notification_type='report_assigned',
                title='Нова пријава доделена',
                message=f'Нова пријава #{instance.id} е доделена на вашиот сектор: {instance.get_sector_display()}.',
                report=instance
            )
    elif instance.citizen and hasattr(instance, '_original_status'):
        # Status changed - notify the citizen who submitted the report
        if instance._original_status != instance.status:
            # Only create notification for resolved status
            if instance.status == 'resolved':
                create_notification(
                    user=instance.citizen,
                    notification_type='status_change',
                    title=f'Пријавата #{instance.id} е решена',
                    message=f'Вашата пријава е успешно решена. Ви благодариме за пријавување!',
                    report=instance
                )
            # Also notify when status changes from resolved back to other states
            elif instance._original_status == 'resolved':
                status_labels = dict(Report.STATUS_CHOICES)
                new_status_label = status_labels.get(instance.status, instance.status)
                
                create_notification(
                    user=instance.citizen,
                    notification_type='status_change',
                    title=f'Статусот на пријава #{instance.id} е променет',
                    message=f'Статусот на вашата пријава е променет од решено на: {new_status_label}',
                    report=instance
                )
