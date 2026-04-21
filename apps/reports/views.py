import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count
from django.db.models.functions import Round
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .forms import ReportCreateForm, ReportSubmissionForm
from .models import MUNICIPALITY_CHOICES, Report


def home(request):
    """Render project landing page."""
    return render(request, "reports/home.html")


def dashboard(request):
    """Render post-login dashboard page."""
    return render(request, "reports/dashboard.html")


@login_required
def submit_report(request):
    """Render submission form and persist a new report on POST.

    GET returns an empty ``ReportSubmissionForm``. POST validates the
    submitted data; on success the report is saved with the current
    user as ``citizen`` and the user is redirected back to the same
    page with a success message. The AI classification pipeline runs
    via a ``post_save`` signal on ``Report`` (see ``apps/reports/signals.py``).
    """
    if request.method == "POST":
        form = ReportSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            report = form.save(commit=False)
            report.citizen = request.user
            report.save()
            messages.success(request, "Вашата пријава е успешно поднесена.")
            return redirect("submit_report")
    else:
        form = ReportSubmissionForm()
    return render(request, "reports/submit_report.html", {"form": form})


def user_is_officer(user):
    return user.groups.filter(name__in=["officer", "officers"]).exists()


def get_user_sector(user):
    if hasattr(user, "profile"):
        return getattr(user.profile, "sector", None)
    return None


@login_required
@require_http_methods(["PATCH"])
def update_report_status(request, report_id):
    """Officer-only endpoint that updates a report's status and internal note."""
    if not user_is_officer(request.user):
        return JsonResponse({"error": "Only officers may update report status."}, status=403)

    report = get_object_or_404(Report, pk=report_id)
    if report.sector != get_user_sector(request.user):
        return JsonResponse({"error": "Officers may only update reports in their own sector."}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    new_status = payload.get("status")
    valid_statuses = {choice[0] for choice in Report.STATUS_CHOICES}
    if not new_status or new_status not in valid_statuses:
        return JsonResponse({"error": "Invalid or missing status."}, status=400)

    report.status = new_status
    report.status_changed_at = timezone.now()
    report.assigned_officer = request.user

    update_fields = ["status", "status_changed_at", "assigned_officer"]
    if "internal_note" in payload:
        report.internal_note = payload.get("internal_note") or ""
        update_fields.append("internal_note")

    report.save(update_fields=update_fields)

    return JsonResponse({
        "id": report.pk,
        "status": report.status,
        "internal_note": report.internal_note,
        "status_changed_at": report.status_changed_at.isoformat(),
        "assigned_officer": request.user.username,
    })


def _serialize_report(report):
    return {
        "id": report.id,
        "description": report.description,
        "latitude": float(report.latitude),
        "longitude": float(report.longitude),
        "image": report.image.url if report.image else None,
        "category": report.category,
        "priority": report.priority,
        "sector": report.sector,
        "status": report.status,
        "ai_processed": report.ai_processed,
        "created_at": report.created_at.isoformat(),
    }


@csrf_exempt
@require_http_methods(["POST"])
def create_report(request):
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)

    if request.content_type and request.content_type.startswith("application/json"):
        try:
            payload = json.loads(request.body.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"errors": {"non_field_errors": ["Invalid JSON payload."]}}, status=400)
        form = ReportCreateForm(payload)
    else:
        form = ReportCreateForm(request.POST, request.FILES)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    report = Report.objects.create(
        citizen=request.user,
        description=form.cleaned_data["description"],
        latitude=form.cleaned_data["latitude"],
        longitude=form.cleaned_data["longitude"],
        image=form.cleaned_data.get("image"),
        status="new",
    )

    report.refresh_from_db()
    return JsonResponse(_serialize_report(report), status=201)


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



@login_required
def map_view(request):
    """Render interactive map page with report filters."""
    municipality_labels = dict(MUNICIPALITY_CHOICES)
    distinct_slugs = (
        Report.objects.exclude(municipality="")
        .values_list("municipality", flat=True)
        .distinct()
    )
    municipalities = sorted(
        ((slug, municipality_labels.get(slug, slug)) for slug in distinct_slugs),
        key=lambda item: item[1],
    )

    context = {
        "category_choices": Report.CATEGORY_CHOICES,
        "status_choices": Report.STATUS_CHOICES,
        "municipalities": municipalities,
    }
    return render(request, "reports/map.html", context)


@login_required
def reports_json(request):
    """Return reports as JSON for AJAX-based Leaflet map rendering."""
    queryset = Report.objects.all().order_by("-created_at")

    category = request.GET.get("category", "").strip()
    status = request.GET.get("status", "").strip()
    municipality = request.GET.get("municipality", "").strip()

    if category:
        queryset = queryset.filter(category=category)
    if status:
        queryset = queryset.filter(status=status)
    if municipality:
        queryset = queryset.filter(municipality=municipality)

    status_labels = dict(Report.STATUS_CHOICES)
    category_labels = dict(Report.CATEGORY_CHOICES)

    data = [
        {
            "id": report.pk,
            "description": report.description,
            "status": report.status,
            "status_label": status_labels.get(report.status, report.status),
            "category": report.category,
            "category_label": category_labels.get(report.category, report.category),
            "municipality": report.municipality or "",
            "lat": float(report.latitude),
            "lng": float(report.longitude),
        }
        for report in queryset
    ]

    return JsonResponse({"results": data})



# # 
@login_required
def officer_panel(request):
    if not user_is_officer(request.user):
        return redirect('dashboard')
    
    sector = get_user_sector(request.user)
    reports = Report.objects.filter(sector=sector).order_by('-created_at')
    
    status_filter = request.GET.get('status')
    if status_filter:
        reports = reports.filter(status=status_filter)
    
    priority_filter = request.GET.get('priority')
    if priority_filter:
        reports = reports.filter(priority=priority_filter)
        
    return render(request, "reports/officer_panel.html", {
        "reports": reports,
        "sector": sector,
    })
