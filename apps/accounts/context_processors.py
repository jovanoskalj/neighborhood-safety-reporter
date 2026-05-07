"""Template context processor for user notification data."""
from .models import UserNotification


def notification_context(request):
    """Add notification data to template context."""
    context = {}
    
    if request.user.is_authenticated:
        unread_count = UserNotification.objects.filter(
            user=request.user, 
            is_read=False
        ).count()
        
        recent_notifications = UserNotification.objects.filter(
            user=request.user
        ).order_by('-created_at')[:5]
        
        context.update({
            'unread_notification_count': unread_count,
            'recent_notifications': recent_notifications,
        })
    
    return context
