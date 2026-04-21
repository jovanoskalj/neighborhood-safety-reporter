import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import Report
from django.http import JsonResponse
from django.db.models import Count
from .models import Report


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


def user_is_officer(user):
    return user.groups.filter(name__in=['officer', 'officers']).exists()


def get_user_sector(user):
    if hasattr(user, 'profile'):
        return getattr(user.profile, 'sector', None)
    return None


@login_required
@require_http_methods(["PATCH"])
def update_report_status(request, report_id):
    if not user_is_officer(request.user):
        return JsonResponse({"error": "Only officers may update report status."}, status=403)

    report = get_object_or_404(Report, pk=report_id)
    if report.sector != get_user_sector(request.user):
        return JsonResponse({"error": "Officers may only update reports in their own sector."}, status=403)

    try:
        payload = json.loads(request.body.decode('utf-8') or '{}')
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    new_status = payload.get('status')
    valid_statuses = {choice[0] for choice in Report.STATUS_CHOICES}
    if not new_status or new_status not in valid_statuses:
        return JsonResponse({"error": "Invalid or missing status."}, status=400)

    report.status = new_status
    report.status_changed_at = timezone.now()
    report.assigned_officer = request.user
    report.save(update_fields=['status', 'status_changed_at', 'assigned_officer'])

    return JsonResponse({
        "id": report.pk,
        "status": report.status,
        "status_changed_at": report.status_changed_at.isoformat(),
        "assigned_officer": request.user.username,
    })

@login_required
def heatmap(request):
    """Returns lat/lng/weight data for Leaflet.heat heatmap plugin."""
    data = Report.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False
    ).annotate(
        lat_bucket=Round('latitude', 3),
        lng_bucket=Round('longitude', 3)
    ).values('lat_bucket', 'lng_bucket').annotate(weight=Count('id'))

    result = [
        [float(item['lat_bucket']), float(item['lng_bucket']), item['weight']]
        for item in data
    ]

    return JsonResponse(result, safe=False)