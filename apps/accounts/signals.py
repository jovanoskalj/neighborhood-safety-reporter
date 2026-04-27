"""Signal handlers for account lifecycle and role groups."""

from django.contrib.auth.models import Group, User
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .models import UserProfile

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
