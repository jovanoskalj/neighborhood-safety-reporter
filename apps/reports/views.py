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