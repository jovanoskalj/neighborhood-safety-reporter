from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from .models import Report
from .services import generate_ai_summary


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
def submit_report(request):
    if request.method == "POST":
        report = Report.objects.create(
            citizen=request.user,
            description=request.POST.get("description"),
            latitude=request.POST.get("latitude"),
            longitude=request.POST.get("longitude"),
        )

        ai_summary = generate_ai_summary(report.description)

        report.internal_note = ai_summary
        report.ai_processed = True
        report.save()

        return redirect("dashboard")

    return render(request, "reports/submit_report.html")
