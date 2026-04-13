from django.contrib.auth.decorators import login_required
from django.shortcuts import render


def home(request):
    """Render project landing page."""
    return render(request, "reports/home.html")


def dashboard(request):
    """Render post-login dashboard page."""
    return render(request, "reports/dashboard.html")


@login_required
def submit_report(request):
    """Render report submission page (login required)."""
    return render(request, "reports/submit_report.html")

@login_required
def notifications_log(request):
    """Render notifications log page (login required)."""
    from apps.notifications.models import Notification
    notifications = Notification.objects.order_by("-time")
    return render(request, "reports/notifications_log.html", {"notifications": notifications})