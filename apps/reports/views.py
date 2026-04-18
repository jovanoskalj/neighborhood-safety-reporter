import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib.auth.decorators import login_required
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.ai_classifier.classifier import classify_report
from .forms import ReportCreateForm
from .models import Report

logger = logging.getLogger(__name__)


def _parse_iso_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _build_report_filters(request):
    filters = Q()
    category = request.GET.get("category")
    status = request.GET.get("status")
    sector = request.GET.get("sector")
    priority = request.GET.get("priority")
    date_from = request.GET.get("from")
    date_to = request.GET.get("to")
    keyword = request.GET.get("keyword")
    latitude = request.GET.get("latitude")
    longitude = request.GET.get("longitude")

    if category:
        filters &= Q(category=category)
    if status:
        filters &= Q(status=status)
    if sector:
        filters &= Q(sector=sector)
    if priority:
        filters &= Q(priority=priority)

    from_date = _parse_iso_date(date_from)
    if from_date:
        filters &= Q(created_at__date__gte=from_date)

    to_date = _parse_iso_date(date_to)
    if to_date:
        filters &= Q(created_at__date__lte=to_date)

    if keyword:
        filters &= Q(description__icontains=keyword)

    if latitude:
        try:
            filters &= Q(latitude=Decimal(latitude))
        except InvalidOperation:
            pass
    if longitude:
        try:
            filters &= Q(longitude=Decimal(longitude))
        except InvalidOperation:
            pass

    return filters


def _is_json_request(request):
    accept = request.headers.get("Accept", "")
    return "application/json" in accept.lower() or request.GET.get("format") == "json"


def _serialize_reports_page(page):
    return {
        "count": page.paginator.count,
        "num_pages": page.paginator.num_pages,
        "page": page.number,
        "results": [_serialize_report(report) for report in page.object_list],
    }


def home(request):
    """Render project landing page or search/filter endpoint."""
    should_filter = _is_json_request(request) or any(
        request.GET.get(param)
        for param in [
            "category",
            "status",
            "sector",
            "priority",
            "from",
            "to",
            "keyword",
            "latitude",
            "longitude",
            "page",
        ]
    )

    if not should_filter:
        return render(request, "reports/home.html")

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

    return render(request, "reports/home.html", {"reports_page": page_obj})


def dashboard(request):
    """Render post-login dashboard page."""
    return render(request, "reports/dashboard.html")


@login_required
def submit_report(request):
    """Render report submission page (login required)."""
    return render(request, "reports/submit_report.html")


def user_is_officer(user):
    return user.groups.filter(name__in=["officer", "officers"]).exists()


def get_user_sector(user):
    if hasattr(user, "profile"):
        return getattr(user.profile, "sector", None)
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
    report.save(update_fields=["status", "status_changed_at", "assigned_officer"])

    return JsonResponse({
        "id": report.pk,
        "status": report.status,
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
@require_http_methods(["POST"])
def reclassify_reports(request):
    if not request.user.is_staff:
        return JsonResponse({"error": "Admin access required."}, status=403)

    reports = Report.objects.filter(status="Unclassified")
    processed = 0
    failed = 0

    for report in reports:
        try:
            result = classify_report(report.description)
            report.category = result["category"]
            report.priority = result["priority"]
            report.sector = result["sector"]
            report.save(update_fields=["category", "priority", "sector"])
            logger.info(f"Reclassified report {report.id}")
            processed += 1
        except Exception as e:
            logger.error(f"Failed to reclassify report {report.id}: {e}")
            failed += 1

    return JsonResponse({"processed": processed, "failed": failed})

