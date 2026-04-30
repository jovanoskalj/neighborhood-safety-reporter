import json
from datetime import datetime
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.models import UserProfile
from apps.ai_classifier.classifier import classify_report
from apps.notifications.services import send_report_created_email, send_report_status_changed_email

from .forms import ReportStatusUpdateForm, ReportSubmissionForm
from .models import Report, ReportStatusHistory


MAX_REPORTS_PER_24H = 10
REPORT_WINDOW_HOURS = 24


def home(request):
    """Render project landing page."""
    return render(request, "reports/home.html")


def _as_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _is_officer(user) -> bool:
    return user.groups.filter(name__in=["officer", "officers"]).exists()


def _serialize_report(report: Report) -> dict:
    return {
        "id": report.id,
        "description": report.description,
        "category": report.category,
        "category_display": report.get_category_display(),
        "priority": report.priority,
        "priority_display": report.get_priority_display(),
        "status": report.status,
        "status_display": report.get_status_display(),
        "sector": report.sector,
        "sector_display": report.get_sector_display(),
        "latitude": _as_float(report.latitude),
        "longitude": _as_float(report.longitude),
        "created_at": report.created_at.isoformat(),
        "updated_at": report.updated_at.isoformat(),
        "status_changed_at": report.status_changed_at.isoformat() if report.status_changed_at else None,
        "detail_url": reverse("report_detail", args=[report.id]),
    }


def _apply_ai_classification(report: Report) -> None:
    result = classify_report(report.description)
    report.category = result.get("category", "other")
    report.priority = result.get("priority", "normal")
    report.sector = result.get("sector", "admin")
    report.status = result.get("status", "new")
    report.ai_processed = True
    report.status_changed_at = timezone.now()


def _parse_json_body(request):
    if "application/json" not in request.content_type:
        return None
    try:
        return json.loads((request.body or b"{}").decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}


def _filter_queryset(request, queryset):
    category = (request.GET.get("category") or "").strip().lower()
    status = (request.GET.get("status") or "").strip().lower()
    sector = (request.GET.get("sector") or "").strip().lower()
    priority = (request.GET.get("priority") or "").strip().lower()
    keyword = (request.GET.get("keyword") or "").strip()
    location = (request.GET.get("location") or "").strip()
    date_from = (request.GET.get("from") or "").strip()
    date_to = (request.GET.get("to") or "").strip()

    if category:
        queryset = queryset.filter(category=category)
    if status:
        queryset = queryset.filter(status=status)
    if sector:
        queryset = queryset.filter(sector=sector)
    if priority:
        queryset = queryset.filter(priority=priority)
    if keyword:
        queryset = queryset.filter(description__icontains=keyword)
    if location:
        queryset = queryset.filter(description__icontains=location)

    if date_from:
        try:
            dt_from = datetime.fromisoformat(date_from)
            queryset = queryset.filter(created_at__gte=dt_from)
        except ValueError:
            pass

    if date_to:
        try:
            dt_to = datetime.fromisoformat(date_to)
            queryset = queryset.filter(created_at__lte=dt_to)
        except ValueError:
            pass

    return queryset


def _visible_reports_for_user(request):
    queryset = Report.objects.select_related("citizen").order_by("-created_at")
    if request.user.is_superuser:
        return queryset

    if _is_officer(request.user):
        profile = UserProfile.objects.filter(user=request.user).first()
        if profile and profile.sector:
            return queryset.filter(sector=profile.sector)
        return queryset.none()

    return queryset.filter(citizen=request.user)


def _can_view_report(user, report: Report) -> bool:
    if user.is_superuser:
        return True
    if report.citizen_id == user.id:
        return True
    if _is_officer(user):
        profile = UserProfile.objects.filter(user=user).first()
        return bool(profile and profile.sector and profile.sector == report.sector)
    return False


def _is_submission_rate_limited(user) -> bool:
    cutoff = timezone.now() - timedelta(hours=REPORT_WINDOW_HOURS)
    recent_reports_count = Report.objects.filter(citizen=user, created_at__gte=cutoff).count()
    return recent_reports_count >= MAX_REPORTS_PER_24H


def _remaining_reports_quota(user) -> int:
    cutoff = timezone.now() - timedelta(hours=REPORT_WINDOW_HOURS)
    recent_reports_count = Report.objects.filter(citizen=user, created_at__gte=cutoff).count()
    return max(0, MAX_REPORTS_PER_24H - recent_reports_count)


def _log_status_transition(report: Report, from_status: str | None, to_status: str, changed_by=None, note: str = "") -> None:
    ReportStatusHistory.objects.create(
        report=report,
        from_status=from_status or "",
        to_status=to_status,
        changed_by=changed_by,
        note=note,
    )


@login_required
def dashboard(request):
    """Citizen dashboard with own reports list + filters + mini map."""
    all_reports = Report.objects.filter(citizen=request.user).order_by("-created_at")
    reports = all_reports

    selected_category = (request.GET.get("category") or "").strip().lower()
    selected_priority = (request.GET.get("priority") or "").strip().lower()
    selected_status = (request.GET.get("status") or "").strip().lower()

    if selected_category:
        reports = reports.filter(category=selected_category)
    if selected_priority:
        reports = reports.filter(priority=selected_priority)
    if selected_status:
        reports = reports.filter(status=selected_status)

    filtered_reports = reports
    paginator = Paginator(filtered_reports, 8)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)
    reports = page_obj.object_list

    map_points = [
        {
            "id": report.id,
            "lat": _as_float(report.latitude),
            "lng": _as_float(report.longitude),
            "status": report.status,
            "category": report.category,
        }
        for report in filtered_reports
    ]

    query_params = request.GET.copy()
    query_params.pop("page", None)

    context = {
        "reports": reports,
        "total_count": all_reports.count(),
        "new_count": all_reports.filter(status="new").count(),
        "in_progress_count": all_reports.filter(status="in_progress").count(),
        "done_count": all_reports.filter(status="resolved").count(),
        "withdrawn_count": all_reports.filter(status="withdrawn").count(),
        "unclassified_count": all_reports.filter(status="unclassified").count(),
        "category_choices": Report.CATEGORY_CHOICES,
        "priority_choices": Report.PRIORITY_CHOICES,
        "status_choices": Report.STATUS_CHOICES,
        "selected_category": selected_category,
        "selected_priority": selected_priority,
        "selected_status": selected_status,
        "map_points": map_points,
        "page_obj": page_obj,
        "query_without_page": query_params.urlencode(),
    }
    return render(request, "reports/dashboard.html", context)


@login_required
def submit_report(request):
    """Render and process report submission form."""
    if request.method == "POST":
        form = ReportSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            if _is_submission_rate_limited(request.user):
                messages.error(
                    request,
                    "Го достигнавте дневниот лимит од 10 пријави за 24 часа. Обидете се повторно утре.",
                )
                return render(
                    request,
                    "reports/submit_report.html",
                    {
                        "form": form,
                        "remaining_quota": _remaining_reports_quota(request.user),
                        "max_reports_per_24h": MAX_REPORTS_PER_24H,
                    },
                    status=429,
                )

            report = form.save(commit=False)
            report.citizen = request.user
            _apply_ai_classification(report)
            report.save()
            _log_status_transition(report, None, report.status, changed_by=request.user, note="Креирана пријава")
            send_report_created_email(report)
            messages.success(request, f"Пријавата #{report.pk} е успешно поднесена.")
            return redirect("my_reports")
    else:
        form = ReportSubmissionForm()

    return render(
        request,
        "reports/submit_report.html",
        {
            "form": form,
            "remaining_quota": _remaining_reports_quota(request.user),
            "max_reports_per_24h": MAX_REPORTS_PER_24H,
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def reports_api(request):
    """GET filtered reports, POST create new report with AI classification."""
    if request.method == "POST":
        payload = _parse_json_body(request)
        if payload is None:
            form = ReportSubmissionForm(request.POST, request.FILES)
        elif not payload:
            return JsonResponse({"errors": {"body": ["Invalid JSON body."]}}, status=400)
        else:
            form = ReportSubmissionForm(payload)

        if not form.is_valid():
            return JsonResponse({"errors": form.errors}, status=400)

        if _is_submission_rate_limited(request.user):
            return JsonResponse(
                {
                    "detail": "Daily limit reached: max 10 reports per 24 hours. Please try again tomorrow.",
                    "limit": MAX_REPORTS_PER_24H,
                    "window_hours": REPORT_WINDOW_HOURS,
                },
                status=429,
            )

        report = form.save(commit=False)
        report.citizen = request.user
        _apply_ai_classification(report)
        report.save()
        _log_status_transition(report, None, report.status, changed_by=request.user, note="Креирана пријава")
        send_report_created_email(report)
        return JsonResponse(_serialize_report(report), status=201)

    queryset = _visible_reports_for_user(request)
    queryset = _filter_queryset(request, queryset)

    page = max(int(request.GET.get("page", 1) or 1), 1)
    per_page = min(max(int(request.GET.get("per_page", 20) or 20), 1), 100)
    paginator = Paginator(queryset, per_page)
    page_obj = paginator.get_page(page)

    return JsonResponse(
        {
            "count": paginator.count,
            "num_pages": paginator.num_pages,
            "current_page": page_obj.number,
            "results": [_serialize_report(report) for report in page_obj.object_list],
        }
    )


@login_required
@require_GET
def my_reports(request):
    """Alias for citizen dashboard route."""
    return dashboard(request)


@login_required
@require_GET
def report_detail(request, report_id: int):
    """Show full details for one report (owner/officer same sector/admin)."""
    report = get_object_or_404(Report, pk=report_id)
    if not _can_view_report(request.user, report):
        return JsonResponse({"detail": "Not allowed."}, status=403)
    status_labels = dict(Report.STATUS_CHOICES)
    timeline = []
    for event in report.status_history.select_related("changed_by").all():
        timeline.append(
            {
                "from_status": event.from_status,
                "to_status": event.to_status,
                "from_status_label": status_labels.get(event.from_status, event.from_status),
                "to_status_label": status_labels.get(event.to_status, event.to_status),
                "changed_by": event.changed_by,
                "changed_at": event.changed_at,
                "note": event.note,
            }
        )

    if not timeline:
        timeline = [
            {
                "from_status": "",
                "to_status": report.status,
                "from_status_label": "",
                "to_status_label": status_labels.get(report.status, report.status),
                "changed_by": None,
                "changed_at": report.created_at,
                "note": "Креирана пријава",
            }
        ]
    return render(request, "reports/report_detail.html", {"report": report, "timeline": timeline})


@login_required
@require_http_methods(["POST"])
def withdraw_report(request, report_id: int):
    """Allow citizens to withdraw their own report."""
    report = get_object_or_404(Report, pk=report_id)
    if report.citizen_id != request.user.id:
        return JsonResponse({"detail": "Only owner can withdraw this report."}, status=403)

    if report.status not in {"new", "unclassified"}:
        messages.warning(request, "Повлекување е дозволено само за пријави со статус Нова или Некласифицирана.")
        return redirect("my_reports")

    old_status = report.status
    report.status = "withdrawn"
    report.status_changed_at = timezone.now()
    report.save(update_fields=["status", "status_changed_at", "updated_at"])
    _log_status_transition(report, old_status, report.status, changed_by=request.user, note="Повлечена од корисник")
    send_report_status_changed_email(report, old_status, report.status)
    messages.success(request, f"Пријавата #{report.id} е повлечена.")
    return redirect("my_reports")


@login_required
def update_report_status(request, report_id: int):
    """Officer status update endpoint; accepts PATCH or POST."""
    if request.method not in {"PATCH", "POST"}:
        return HttpResponseNotAllowed(["PATCH", "POST"])

    report = get_object_or_404(Report, pk=report_id)

    if not _is_officer(request.user):
        return JsonResponse({"detail": "Only officers can update status."}, status=403)

    profile = UserProfile.objects.filter(user=request.user).first()
    if not profile or not profile.sector or profile.sector != report.sector:
        return JsonResponse({"detail": "You can only edit reports from your own sector."}, status=403)

    if request.method == "PATCH":
        payload = _parse_json_body(request)
        if payload is None:
            payload = {}
    else:
        payload = request.POST

    old_status = report.status
    form = ReportStatusUpdateForm(payload, instance=report)
    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    requested_status = (payload.get("status") or "").strip() if hasattr(payload, "get") else ""
    valid_statuses = {value for value, _ in Report.STATUS_CHOICES}
    updated_report = form.save(commit=False)
    if requested_status in valid_statuses:
        updated_report.status = requested_status
    updated_report.assigned_officer = request.user
    if old_status != updated_report.status:
        updated_report.status_changed_at = timezone.now()
    updated_report.save()

    if old_status != updated_report.status:
        _log_status_transition(
            updated_report,
            old_status,
            updated_report.status,
            changed_by=request.user,
            note="Промена од службеник",
        )
        send_report_status_changed_email(updated_report, old_status, updated_report.status)

    return JsonResponse(_serialize_report(updated_report))


@login_required
@require_GET
def map_view(request):
    """Interactive map page with report pins + filters."""
    return render(
        request,
        "reports/map.html",
        {
            "category_choices": Report.CATEGORY_CHOICES,
            "status_choices": Report.STATUS_CHOICES,
            "sector_choices": Report.SECTOR_CHOICES,
            "priority_choices": Report.PRIORITY_CHOICES,
        },
    )


@login_required
@require_GET
def heatmap_data(request):
    """Return aggregated heatmap points as {lat,lng,weight}."""
    queryset = _visible_reports_for_user(request)
    buckets = {}

    for report in queryset:
        lat = round(_as_float(report.latitude) or 0.0, 3)
        lng = round(_as_float(report.longitude) or 0.0, 3)
        key = (lat, lng)
        buckets[key] = buckets.get(key, 0) + 1

    points = [{"lat": lat, "lng": lng, "weight": weight} for (lat, lng), weight in buckets.items()]
    return JsonResponse(points, safe=False)