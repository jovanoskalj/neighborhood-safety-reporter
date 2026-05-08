"""Citizen / officer / API views for the reports app.

Admin dashboard CRUD lives in `admin_views.py`; pure helpers in `_view_helpers.py`.
This module re-exports admin views so `urls.py` (which references `views.X`) keeps working.

`send_report_status_changed_email` is imported here (rather than called from a
helper module) so tests that `patch("apps.reports.views.send_report_status_changed_email")`
intercept it via this module's globals.

Report creation is centralised in `_persist_new_report`. The post_save signal
in `apps/reports/signals.py` handles AI classification — both `create_report`
(JSON) and `submit_report` (HTML form) go through the same path.
"""
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.models import UserProfile
from apps.accounts.utils import notify_report_reassigned
from apps.notifications.senders import send_status_change_email
from apps.notifications.services import send_report_created_email, send_report_status_changed_email

from ._view_helpers import (
    MAX_REPORTS_PER_24H,
    REPORT_WINDOW_HOURS,
    SEARCH_PARAMS,
    _as_float,
    _build_report_filters,
    _can_view_report,
    _filter_queryset,
    _is_json_request,
    _is_officer,
    _is_submission_rate_limited,
    _log_status_transition,
    _parse_json_body,
    _remaining_reports_quota,
    _serialize_report,
    _serialize_reports_page,
    _visible_reports_for_user,
    _write_audit_log,
)
from .admin_views import (  # noqa: F401
    admin_classify_report,
    create_category,
    create_sector,
    create_user,
    dashboard,
    delete_category,
    delete_sector,
    delete_user,
    export_reports_csv,
    export_reports_excel,
    import_reports,
    review_duplicate_report,
    toggle_user_active,
    update_category,
    update_sector,
    update_user,
)
from .duplicate_detection import find_potential_duplicate
from .forms import ReportCreateForm, ReportSubmissionForm
from .models import MUNICIPALITY_CHOICES, Report, ReportCategory, Sector

_CATEGORY_TO_SECTOR_FALLBACK = {
    "infrastructure": "infrastructure",
    "utilities": "utilities",
    "safety": "safety",
    "health": "health",
    "other": "admin",
}


def _persist_new_report(citizen, *, description, latitude, longitude, image=None,
                        category=None, priority=None, municipality=None):
    """Save a Report, run duplicate detection, log creation, send email.

    Returns ``(report, duplicate)`` where ``duplicate`` is the matched Report
    or ``None``. Callers decide how to surface the duplicate (HTML message vs
    JSON field). Classification is handled by the post_save signal in
    `apps/reports/signals.py`.
    """
    duplicate = find_potential_duplicate(
        description=description,
        latitude=float(latitude),
        longitude=float(longitude),
    )
    extra = {}
    if category:
        extra["category"] = category
    if priority:
        extra["priority"] = priority
    if municipality:
        extra["municipality"] = municipality
    if duplicate is not None:
        extra["is_duplicate"] = True
        extra["duplicate_of"] = duplicate
        extra["duplicate_verdict"] = "pending"

    report = Report.objects.create(
        citizen=citizen,
        description=description,
        latitude=latitude,
        longitude=longitude,
        image=image,
        **extra,
    )

    # When AI is disabled the post_save signal returns early; backfill sector
    # from category so reports still route to the correct team.
    if not getattr(settings, "AI_CLASSIFICATION_ENABLED", False):
        derived_sector = _CATEGORY_TO_SECTOR_FALLBACK.get(report.category, "admin")
        if derived_sector != report.sector:
            Report.objects.filter(pk=report.pk).update(sector=derived_sector)

    report.refresh_from_db()
    _log_status_transition(report, None, report.status, changed_by=citizen, note="Креирана пријава")
    send_report_created_email(report)
    return report, duplicate

logger = logging.getLogger(__name__)


def create_report(request):
    """JSON endpoint to create a report.

    Returns 401 (not 302 redirect) when unauthenticated so it's safe for SPA/API
    clients. Accepts both ``application/json`` and form-encoded bodies.
    """
    if not request.user.is_authenticated:
        return JsonResponse({"detail": "Authentication required."}, status=401)
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])

    payload = _parse_json_body(request)
    if payload is None:
        form = ReportCreateForm(request.POST, request.FILES)
    elif not payload:
        return JsonResponse({"errors": {"body": ["Invalid JSON body."]}}, status=400)
    else:
        form = ReportCreateForm(payload)

    if not form.is_valid():
        return JsonResponse({"errors": form.errors}, status=400)

    if _is_submission_rate_limited(request.user):
        return JsonResponse(
            {
                "detail": "Daily limit reached: max 10 reports per 24 hours.",
                "limit": MAX_REPORTS_PER_24H,
                "window_hours": REPORT_WINDOW_HOURS,
            },
            status=429,
        )

    report, _duplicate = _persist_new_report(
        request.user,
        description=form.cleaned_data["description"],
        latitude=form.cleaned_data["latitude"],
        longitude=form.cleaned_data["longitude"],
        image=form.cleaned_data.get("image"),
    )
    return JsonResponse(_serialize_report(report), status=201)


def home(request):
    """Landing page (no params) or paginated search endpoint (with params)."""
    should_filter = _is_json_request(request) or any(
        request.GET.get(param) for param in SEARCH_PARAMS
    )

    if not should_filter:
        if request.user.is_authenticated and request.user.is_superuser:
            return redirect("/dashboard/")
        return render(request, "reports/home.html")

    if not request.user.is_authenticated:
        if _is_json_request(request):
            return JsonResponse({"detail": "Authentication required."}, status=401)
        return redirect(f"{reverse('login')}?next={request.get_full_path()}")

    filters = _build_report_filters(request)
    queryset = Report.objects.filter(filters).order_by("-created_at")

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page", 1)
    try:
        page_obj = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    if _is_json_request(request):
        return JsonResponse(_serialize_reports_page(page_obj), status=200)

    return render(
        request,
        "reports/search_results.html",
        {"reports_page": page_obj, "query": request.GET},
    )


@login_required
def submit_report(request):
    """Render and process the citizen report-submission form (HTML)."""
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

            report, duplicate = _persist_new_report(
                request.user,
                description=form.cleaned_data["description"],
                latitude=form.cleaned_data["latitude"],
                longitude=form.cleaned_data["longitude"],
                image=form.cleaned_data.get("image"),
                category=form.cleaned_data.get("category"),
                priority=form.cleaned_data.get("priority"),
                municipality=form.cleaned_data.get("municipality"),
            )
            if duplicate is not None:
                messages.warning(
                    request,
                    f"Можно е оваа пријава да е дупликат на пријава #{duplicate.pk}. Администратор ќе одлучи дали навистина е дупликат.",
                )
            messages.success(request, "Вашата пријава е успешно поднесена.")
            return redirect("report_detail", report_id=report.id)
        messages.error(request, "Ве молиме поправете ги грешките во формата.")
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
@require_GET
def reports_api(request):
    """List visible reports as paginated JSON. POST creation lives in `create_report`."""
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
    if _is_officer(request.user):
        return redirect("officer_panel")
    if request.user.is_authenticated:
        base_qs = Report.objects.filter(citizen=request.user)
    else:
        base_qs = Report.objects.none()

    total_count = base_qs.count()
    new_count = base_qs.filter(status="new").count()
    in_progress_count = base_qs.filter(status="in_progress").count()
    done_count = base_qs.filter(status="resolved").count()
    duplicate_count = base_qs.filter(duplicate_verdict__in=["pending", "confirmed"]).count()

    qs = base_qs.select_related("duplicate_of", "duplicate_of__citizen")

    category = request.GET.get("category", "")
    priority = request.GET.get("priority", "")
    status = request.GET.get("status", "")

    if category:
        qs = qs.filter(category=category)
    if priority:
        qs = qs.filter(priority=priority)
    if status:
        qs = qs.filter(status=status)

    map_points = [
        {
            "id": r.id,
            "lat": float(r.latitude),
            "lng": float(r.longitude),
            "category": r.get_category_display(),
            "status": r.get_status_display(),
            "status_key": r.status,
        }
        for r in qs
    ]

    return render(
        request,
        "reports/my_reports.html",
        {
            "reports": qs,
            "map_points": map_points,
            "total_count": total_count,
            "new_count": new_count,
            "in_progress_count": in_progress_count,
            "done_count": done_count,
            "duplicate_count": duplicate_count,
            "category_choices": Report.CATEGORY_CHOICES,
            "priority_choices": Report.PRIORITY_CHOICES,
            "status_choices": Report.STATUS_CHOICES,
            "selected_category": category,
            "selected_priority": priority,
            "selected_status": status,
        },
    )


@login_required
@require_GET
def report_detail(request, report_id: int):
    """Show full details for one report (owner/officer same sector/admin)."""
    report = get_object_or_404(
        Report.objects.select_related("citizen", "duplicate_of", "duplicate_of__citizen"),
        pk=report_id,
    )
    if not _can_view_report(request.user, report):
        return JsonResponse({"detail": "Not allowed."}, status=403)
    can_view_duplicate_original = bool(
        report.duplicate_of_id and _can_view_report(request.user, report.duplicate_of)
    )
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
    detail_back_url_name = "officer_panel" if _is_officer(request.user) else "my_reports"
    return render(
        request,
        "reports/report_detail.html",
        {
            "report": report,
            "timeline": timeline,
            "can_view_duplicate_original": can_view_duplicate_original,
            "detail_back_url_name": detail_back_url_name,
        },
    )


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
    if profile.municipality and profile.municipality != report.municipality:
        return JsonResponse({"detail": "You can only edit reports from your assigned municipality."}, status=403)

    payload = _parse_json_body(request) if request.method == "PATCH" else request.POST
    if payload is None:
        payload = {}

    requested_status = (payload.get("status") or "").strip()
    valid_statuses = {value for value, _ in Report.STATUS_CHOICES}
    if requested_status and requested_status not in valid_statuses:
        return JsonResponse({"errors": {"status": ["Invalid status."]}}, status=400)

    old_status = report.status
    update_fields = []

    if requested_status:
        report.status = requested_status
        report.status_changed_at = timezone.now()
        update_fields.extend(["status", "status_changed_at"])

    if "internal_note" in payload:
        report.internal_note = payload.get("internal_note") or ""
        update_fields.append("internal_note")

    report.assigned_officer = request.user
    update_fields.append("assigned_officer")

    if update_fields:
        report.save(update_fields=update_fields)

    if requested_status and old_status != report.status:
        _log_status_transition(
            report,
            old_status,
            report.status,
            changed_by=request.user,
            note="Промена од службеник",
        )
        html_email_sent = send_report_status_changed_email(report, old_status, report.status)
        notification = send_status_change_email(report)
        email_sent = bool(html_email_sent or (notification and notification.status == "sent"))

    payload = _serialize_report(report)
    payload["internal_note"] = report.internal_note
    if requested_status and old_status != report.status:
        payload["status_changed"] = True
        payload["old_status"] = old_status
        payload["old_status_label"] = dict(Report.STATUS_CHOICES).get(old_status, old_status)
        payload["email_sent"] = email_sent
        payload["email_recipient"] = getattr(report.citizen, "email", "") or ""
    else:
        payload["status_changed"] = False
        payload["email_sent"] = False
    return JsonResponse(payload)


@login_required
@require_http_methods(["POST"])
def reassign_report_sector(request, report_id: int):
    """Allow an officer to send a wrongly assigned report to another sector."""
    if not _is_officer(request.user):
        return JsonResponse({"detail": "Only officers can reassign reports."}, status=403)

    report = get_object_or_404(Report, pk=report_id)
    profile = UserProfile.objects.filter(user=request.user).first()
    if not profile or not profile.sector or profile.sector != report.sector:
        return JsonResponse({"detail": "You can only reassign reports from your own sector."}, status=403)
    if profile.municipality and profile.municipality != report.municipality:
        return JsonResponse({"detail": "You can only reassign reports from your assigned municipality."}, status=403)

    new_sector = (request.POST.get("sector") or "").strip()
    valid_sectors = set(Sector.objects.filter(is_active=True).values_list("key", flat=True)) | {
        value for value, _ in Report.SECTOR_CHOICES
    }
    if not new_sector or new_sector not in valid_sectors:
        return JsonResponse({"errors": {"sector": ["Invalid sector."]}}, status=400)
    if new_sector == report.sector:
        return JsonResponse({"errors": {"sector": ["Choose a different sector."]}}, status=400)

    old_sector = report.sector
    report.sector = new_sector
    report.assigned_officer = None
    report.save(update_fields=["sector", "assigned_officer", "updated_at"])

    _write_audit_log(
        request,
        action="reassign_report_sector",
        target_model="Report",
        target_id=report.id,
        details={"old_sector": old_sector, "new_sector": new_sector},
    )
    notify_report_reassigned(report, old_sector, reassigned_by=request.user)

    return JsonResponse(
        {
            "id": report.id,
            "old_sector": old_sector,
            "new_sector": report.sector,
            "detail": "Report reassigned.",
        }
    )


@login_required
def map_view(request):
    """Render interactive map page with report filters."""
    active_sector_choices = list(Sector.objects.filter(is_active=True).values_list('key', 'name'))
    context = {
        "category_choices": Report.CATEGORY_CHOICES,
        "status_choices": Report.STATUS_CHOICES,
        "sector_choices": active_sector_choices,
        "priority_choices": Report.PRIORITY_CHOICES,
        "municipality_choices": MUNICIPALITY_CHOICES,
    }
    return render(request, "reports/map.html", context)


@login_required
def reports_json(request):
    """Return reports as JSON for AJAX-based Leaflet map rendering."""
    queryset = _filter_queryset(request, _visible_reports_for_user(request).order_by("-created_at"))

    status_labels = dict(Report.STATUS_CHOICES)
    category_labels = dict(Report.CATEGORY_CHOICES)
    priority_labels = dict(Report.PRIORITY_CHOICES)
    sector_labels = dict(Report.SECTOR_CHOICES)

    data = [
        {
            "id": report.pk,
            "description": report.description,
            "status": report.status,
            "status_label": status_labels.get(report.status, report.status),
            "category": report.category,
            "category_label": category_labels.get(report.category, report.category),
            "priority": report.priority,
            "priority_label": priority_labels.get(report.priority, report.priority),
            "sector": report.sector,
            "sector_label": sector_labels.get(report.sector, report.sector),
            "municipality": report.municipality or "",
            "lat": float(report.latitude),
            "lng": float(report.longitude),
            "created_at": report.created_at.isoformat(),
            "detail_url": reverse("report_detail", args=[report.id]),
        }
        for report in queryset
    ]

    return JsonResponse({"results": data})


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


@login_required
def officer_panel(request):
    if not _is_officer(request.user):
        return redirect("dashboard")

    profile = UserProfile.objects.filter(user=request.user).first()
    sector = profile.sector if profile else None
    reports = Report.objects.filter(sector=sector).select_related("duplicate_of").order_by("-created_at")
    if profile and profile.municipality:
        reports = reports.filter(municipality=profile.municipality)

    status_filter = request.GET.get("status")
    if status_filter:
        reports = reports.filter(status=status_filter)

    priority_filter = request.GET.get("priority")
    if priority_filter:
        reports = reports.filter(priority=priority_filter)

    active_sector_choices = list(Sector.objects.filter(is_active=True).values_list("key", "name"))
    destination_sector_choices = [
        (key, name) for key, name in active_sector_choices if key != sector
    ]

    return render(
        request,
        "reports/officer_panel.html",
        {
            "reports": reports,
            "sector": sector,
            "municipality": profile.municipality if profile else "",
            "status_choices": Report.STATUS_CHOICES,
            "priority_choices": Report.PRIORITY_CHOICES,
            "category_choices": Report.CATEGORY_CHOICES,
            "sector_choices": active_sector_choices,
            "destination_sector_choices": destination_sector_choices,
            "municipality_choices": MUNICIPALITY_CHOICES,
        },
    )


@login_required
def search_page(request):
    """Search visible reports, with keyword matching report descriptions."""
    filters = _build_report_filters(request)
    opshtina = request.GET.get("opshtina", "").strip()
    if opshtina:
        filters &= Q(municipality=opshtina)

    queryset = _visible_reports_for_user(request).filter(filters).order_by("-created_at")
    sort = request.GET.get("sort", "date")
    sort_map = {
        "date": "-created_at",
        "priority": "priority",
        "status": "status",
    }
    queryset = queryset.order_by(sort_map.get(sort, "-created_at"))
    paginator = Paginator(queryset, 20)
    page_number = request.GET.get("page", 1)
    try:
        page_obj = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    active_sector_choices = list(Sector.objects.filter(is_active=True).values_list('key', 'name'))
    active_category_choices = list(ReportCategory.objects.filter(is_active=True).values_list('key', 'name'))

    return render(
        request,
        "reports/search_results.html",
        {
            "reports_page": page_obj,
            "query": request.GET,
            "status_choices": Report.STATUS_CHOICES,
            "priority_choices": Report.PRIORITY_CHOICES,
            "sector_choices": active_sector_choices,
            "category_choices": active_category_choices,
            "municipalities": MUNICIPALITY_CHOICES,
        },
    )
