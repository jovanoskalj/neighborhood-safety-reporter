"""Admin-only views for the notifications log page (task T-22)."""
from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods

from .models import Notification
from .senders import retry_notification


def _is_admin(user) -> bool:
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name__in=["admin", "administrators"]).exists()


def _admin_required(view):
    """Reject non-admins with 403 instead of bouncing them to the login page."""

    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        if not _is_admin(request.user):
            return JsonResponse(
                {"detail": "Admin access required."}, status=403
            ) if request.headers.get("Accept", "").startswith("application/json") \
              else _forbidden(request)
        return view(request, *args, **kwargs)

    return _wrapped


def _forbidden(request):
    from django.http import HttpResponseForbidden
    return HttpResponseForbidden("Admin access required.")


@login_required
@_admin_required
def notifications_log(request):
    """Render the notifications log table."""
    notifications = Notification.objects.order_by("-time")
    return render(
        request,
        "reports/notifications_log.html",
        {"notifications": notifications},
    )


@login_required
@_admin_required
@require_http_methods(["POST"])
def retry(request, notification_id):
    """Re-send a single failed/pending notification."""
    notification = get_object_or_404(Notification, pk=notification_id)
    retry_notification(notification)
    return JsonResponse({
        "id": notification.pk,
        "status": notification.status,
        "status_label": notification.get_status_display(),
    })


@login_required
@_admin_required
@require_http_methods(["POST"])
def retry_all_failed(request):
    """Bulk-retry every notification in ``failed`` state."""
    failed = list(Notification.objects.filter(status="failed"))
    for notification in failed:
        retry_notification(notification)
    succeeded = sum(1 for n in failed if n.status == "sent")
    return JsonResponse({
        "retried": len(failed),
        "succeeded": succeeded,
        "still_failed": len(failed) - succeeded,
    })
