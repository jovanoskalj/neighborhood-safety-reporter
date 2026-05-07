"""Custom template filters for account/role checks."""

from django import template

register = template.Library()


@register.filter
def has_group(user, group_name: str) -> bool:
    """Return True if user belongs to the provided group name."""
    if not getattr(user, "is_authenticated", False):
        return False
    return user.groups.filter(name=group_name).exists()
