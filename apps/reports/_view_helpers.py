"""Shared helpers for the reports views.

Pure utilities and lookups used by both `views.py` (citizen/officer/api views)
and `admin_views.py` (admin dashboard CRUD/import/export). Functions in this
module must NOT call names that tests patch via `apps.reports.views.X` — those
callers stay in `views.py` so the patch resolves correctly.
"""
import csv
import json
import os
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from io import TextIOWrapper
from typing import Optional

from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.text import slugify

from apps.accounts.models import AuditLog, UserProfile

from .models import MUNICIPALITY_CHOICES, Report, ReportCategory, ReportStatusHistory, Sector

MAX_REPORTS_PER_24H = 10
REPORT_WINDOW_HOURS = 24

SEARCH_PARAMS = (
    "category", "status", "sector", "priority",
    "from", "to", "keyword",
    "lat_min", "lat_max", "lng_min", "lng_max",
    "page",
)

REPORT_EXPORT_COLUMNS = [
    "id",
    "description",
    "category",
    "priority",
    "status",
    "sector",
    "location",
    "latitude",
    "longitude",
    "municipality",
    "citizen",
    "created_at",
    "updated_at",
    "status_changed_at",
]

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False


def _parse_iso_date(value):
    """Return a ``date`` parsed from ISO-8601 input, or ``None`` on failure."""
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        return None


def _parse_decimal(value):
    """Return a ``Decimal`` or ``None`` if the input is absent/invalid."""
    if value is None or value == "":
        return None
    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None


def _build_report_filters(request):
    """Translate GET parameters into a ``Q()`` expression."""
    filters = Q()

    for param, field in (
        ("category", "category"),
        ("status", "status"),
        ("sector", "sector"),
        ("priority", "priority"),
    ):
        value = request.GET.get(param)
        if value:
            filters &= Q(**{field: value})

    from_date = _parse_iso_date(request.GET.get("from"))
    if from_date:
        filters &= Q(created_at__date__gte=from_date)

    to_date = _parse_iso_date(request.GET.get("to"))
    if to_date:
        filters &= Q(created_at__date__lte=to_date)

    keyword = request.GET.get("keyword")
    if keyword:
        clean_keyword = keyword.strip()
        if clean_keyword.upper().startswith("ПРЈ-"):
            clean_keyword = clean_keyword[4:]
        matching_slugs = [
            slug for slug, label in MUNICIPALITY_CHOICES
            if keyword.lower() in label.lower()
        ]
        filters &= (
            Q(description__icontains=keyword) |
            Q(id__icontains=clean_keyword) |
            Q(municipality__in=matching_slugs) |
            Q(category__icontains=keyword)
        )
    for param, lookup in (
        ("lat_min", "latitude__gte"),
        ("lat_max", "latitude__lte"),
        ("lng_min", "longitude__gte"),
        ("lng_max", "longitude__lte"),
    ):
        value = _parse_decimal(request.GET.get(param))
        if value is not None:
            filters &= Q(**{lookup: value})

    return filters


def _is_json_request(request):
    """True if caller prefers JSON (via Accept header or ``?format=json``)."""
    accept = request.headers.get("Accept", "")
    return "application/json" in accept.lower() or request.GET.get("format") == "json"


def _serialize_reports_page(page):
    return {
        "count": page.paginator.count,
        "num_pages": page.paginator.num_pages,
        "page": page.number,
        "results": [_serialize_report(report) for report in page.object_list],
    }


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
        "ai_processed": report.ai_processed,
        "created_at": report.created_at.isoformat(),
        "updated_at": report.updated_at.isoformat(),
        "status_changed_at": report.status_changed_at.isoformat() if report.status_changed_at else None,
        "detail_url": reverse("report_detail", args=[report.id]),
    }


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
    municipality = (request.GET.get("municipality") or "").strip().lower()
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
    if municipality:
        queryset = queryset.filter(municipality=municipality)
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


def _filtered_admin_reports(request):
    return _filter_queryset(request, Report.objects.select_related("citizen").order_by("-created_at"))


def _format_report_row(report):
    latitude = str(report.latitude)
    longitude = str(report.longitude)
    return [
        report.id,
        report.description,
        report.category,
        report.priority,
        report.status,
        report.sector,
        f"{latitude},{longitude}",
        latitude,
        longitude,
        report.municipality,
        report.citizen.username,
        report.created_at.isoformat(),
        report.updated_at.isoformat(),
        report.status_changed_at.isoformat() if report.status_changed_at else "",
    ]


def _clean_import_header(value):
    return str(value or "").strip().lower().replace(" ", "_")


def _parse_import_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return timezone.make_aware(value) if timezone.is_naive(value) else value
    if isinstance(value, date):
        return timezone.make_aware(datetime.combine(value, datetime.min.time()))

    parsed = parse_datetime(str(value).strip())
    if parsed:
        return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed
    parsed_date = _parse_iso_date(str(value).strip())
    if parsed_date:
        return timezone.make_aware(datetime.combine(parsed_date, datetime.min.time()))
    return None


def _parse_import_location(row):
    latitude = row.get("latitude") or row.get("lat")
    longitude = row.get("longitude") or row.get("lng") or row.get("lon")
    if (not latitude or not longitude) and row.get("location"):
        pieces = [piece.strip() for piece in str(row["location"]).split(",")]
        if len(pieces) >= 2:
            latitude, longitude = pieces[0], pieces[1]
    return _parse_decimal(latitude), _parse_decimal(longitude)


def _read_import_rows(uploaded_file):
    extension = os.path.splitext(uploaded_file.name)[1].lower()
    if extension == ".csv":
        text_file = TextIOWrapper(uploaded_file.file, encoding="utf-8-sig", newline="")
        return list(csv.DictReader(text_file))

    if extension in {".xlsx", ".xlsm"} and OPENPYXL_AVAILABLE:
        workbook = openpyxl.load_workbook(uploaded_file, read_only=True, data_only=True)
        sheet = workbook.active
        rows = list(sheet.iter_rows(values_only=True))
        if not rows:
            return []
        headers = [_clean_import_header(value) for value in rows[0]]
        return [
            {headers[index]: value for index, value in enumerate(row) if index < len(headers)}
            for row in rows[1:]
            if any(value not in (None, "") for value in row)
        ]

    raise ValueError("Поддржани формати се CSV и XLSX.")


def _import_reports_from_rows(rows, user):
    valid_categories = {choice[0] for choice in Report.CATEGORY_CHOICES} | set(
        ReportCategory.objects.values_list("key", flat=True)
    )
    valid_priorities = {choice[0] for choice in Report.PRIORITY_CHOICES}
    valid_statuses = {choice[0] for choice in Report.STATUS_CHOICES}
    active_sector_keys = set(Sector.objects.values_list("key", flat=True)) | {choice[0] for choice in Report.SECTOR_CHOICES}
    valid_municipalities = {choice[0] for choice in MUNICIPALITY_CHOICES}

    inserted = 0
    skipped_duplicates = []
    invalid_rows = []

    for index, raw_row in enumerate(rows, start=2):
        row = {_clean_import_header(key): value for key, value in raw_row.items()}
        errors = []
        report_id = str(row.get("id") or "").strip()
        description = str(row.get("description") or "").strip()
        category = str(row.get("category") or "").strip().lower()
        priority = str(row.get("priority") or "").strip().lower()
        status = str(row.get("status") or "").strip().lower()
        sector = str(row.get("sector") or "").strip().lower()
        municipality = str(row.get("municipality") or "").strip().lower()
        latitude, longitude = _parse_import_location(row)

        report_pk = None
        if report_id:
            try:
                report_pk = int(report_id)
            except ValueError:
                errors.append("invalid id")

        if report_pk and Report.objects.filter(pk=report_pk).exists():
            skipped_duplicates.append(report_id)
            continue
        if not description:
            errors.append("missing description")
        if category not in valid_categories:
            errors.append("invalid category")
        if priority not in valid_priorities:
            errors.append("invalid priority")
        if status not in valid_statuses:
            errors.append("invalid status")
        if sector not in active_sector_keys:
            errors.append("invalid sector")
        if municipality and municipality not in valid_municipalities:
            errors.append("invalid municipality")
        if latitude is None or longitude is None:
            errors.append("invalid location")

        created_at = _parse_import_datetime(row.get("created_at"))
        updated_at = _parse_import_datetime(row.get("updated_at"))
        status_changed_at = _parse_import_datetime(row.get("status_changed_at"))

        if errors:
            invalid_rows.append({"row": index, "reason": ", ".join(errors)})
            continue

        report = Report(
            citizen=user,
            description=description,
            latitude=latitude,
            longitude=longitude,
            category=category,
            priority=priority,
            status=status,
            sector=sector,
            municipality=municipality,
            status_changed_at=status_changed_at,
            ai_processed=True,
        )
        if report_pk:
            report.id = report_pk
        report.save()

        update_fields = []
        if created_at:
            report.created_at = created_at
            update_fields.append("created_at")
        if updated_at:
            report.updated_at = updated_at
            update_fields.append("updated_at")
        if update_fields:
            Report.objects.filter(pk=report.pk).update(**{field: getattr(report, field) for field in update_fields})
        inserted += 1

    return inserted, skipped_duplicates, invalid_rows


def _visible_reports_for_user(request):
    queryset = Report.objects.select_related("citizen").order_by("-created_at")
    if _is_admin_user(request.user):
        return queryset

    if _is_officer(request.user):
        profile = UserProfile.objects.filter(user=request.user).first()
        if profile and profile.sector:
            queryset = queryset.filter(sector=profile.sector)
            if profile.municipality:
                queryset = queryset.filter(municipality=profile.municipality)
            return queryset
        return queryset.none()

    return queryset.filter(citizen=request.user)


def _can_view_report(user, report: Report) -> bool:
    if user.is_superuser:
        return True
    if report.citizen_id == user.id:
        return True
    if _is_officer(user):
        profile = UserProfile.objects.filter(user=user).first()
        if not profile or not profile.sector or profile.sector != report.sector:
            return False
        return not profile.municipality or profile.municipality == report.municipality
    return False


def _is_submission_rate_limited(user) -> bool:
    cutoff = timezone.now() - timedelta(hours=REPORT_WINDOW_HOURS)
    recent_reports_count = Report.objects.filter(citizen=user, created_at__gte=cutoff).count()
    return recent_reports_count >= MAX_REPORTS_PER_24H


def _remaining_reports_quota(user) -> int:
    cutoff = timezone.now() - timedelta(hours=REPORT_WINDOW_HOURS)
    recent_reports_count = Report.objects.filter(citizen=user, created_at__gte=cutoff).count()
    return max(0, MAX_REPORTS_PER_24H - recent_reports_count)


def _log_status_transition(report: Report, from_status: Optional[str], to_status: str, changed_by=None, note: str = "") -> None:
    ReportStatusHistory.objects.create(
        report=report,
        from_status=from_status or "",
        to_status=to_status,
        changed_by=changed_by,
        note=note,
    )


def _is_admin_user(user: User) -> bool:
    """Allow dashboard access to superusers and admin group users."""
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name__in=["admin", "administrators"]).exists()


def _admin_only() -> callable:
    """Decorator for admin-only endpoints."""
    return user_passes_test(_is_admin_user)


def _write_audit_log(request, action, target_model, target_id, details):
    """Persist admin action to system log."""
    AuditLog.objects.create(
        user=request.user,
        action=action,
        target_model=target_model,
        target_id=target_id,
        details=details,
    )


def _build_unique_key(model, raw_name):
    """Generate a unique slug key for settings entities based on name."""
    base_key = slugify(raw_name)[:45] or "item"
    key = base_key
    counter = 2

    while model.objects.filter(key=key).exists():
        suffix = f"-{counter}"
        key = f"{base_key[:50 - len(suffix)]}{suffix}"
        counter += 1

    return key
