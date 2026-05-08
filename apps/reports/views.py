import csv
import io
import json
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.http import HttpRequest, HttpResponse, HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from apps.accounts.models import AuditLog, UserProfile
# from apps.ai_classifier.classifier import classify_report
from apps.notifications.senders import send_status_change_email
from apps.notifications.services import send_report_created_email, send_report_status_changed_email
from apps.reports import signals

from .duplicate_detection import find_potential_duplicate
from .forms import (
    AdminUserCreateForm,
    ReportCategoryForm,
    ReportCreateForm,
    ReportStatusUpdateForm,
    ReportSubmissionForm,
    SectorForm,
)
from .models import MUNICIPALITY_CHOICES, Report, ReportCategory, ReportStatusHistory, Sector

MAX_REPORTS_PER_24H = 10
REPORT_WINDOW_HOURS = 24

REPORT_EXPORT_COLUMNS = ['ID', 'Description', 'Category', 'Priority', 'Status', 'Sector', 'Latitude', 'Longitude', 'Created At']

SEARCH_PARAMS = (
    "category", "status", "sector", "priority",
    "lat_min", "lat_max", "lng_min", "lng_max",
    "page",
)


def _parse_decimal(value):
    """Return a ``Decimal`` or ``None`` if the input is absent/invalid."""
    if value is None or value == "":
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def _filtered_admin_reports(request):
    """Build filtered queryset for admin export based on GET parameters."""
    queryset = Report.objects.all().order_by('-created_at')
    
    date_from = request.GET.get('from')
    if date_from:
        queryset = queryset.filter(created_at__date__gte=date_from)
    
    date_to = request.GET.get('to')
    if date_to:
        queryset = queryset.filter(created_at__date__lte=date_to)
    
    category = request.GET.get('category')
    if category:
        queryset = queryset.filter(category=category)
    
    status = request.GET.get('status')
    if status:
        queryset = queryset.filter(status=status)
    
    return queryset


def _format_report_row(report):
    """Format a report for CSV/Excel export."""
    return [
        report.id,
        report.description,
        report.category,
        report.priority,
        report.status,
        report.sector,
        report.latitude,
        report.longitude,
        report.created_at.strftime('%Y-%m-%d %H:%M')
    ]


def _parse_decimal(value):
    """Return a ``Decimal`` or ``None`` if the input is absent/invalid."""
    if value is None or value == "":
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
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


try:
    import openpyxl

    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False


def home(request):
    """Landing page (no params) or paginated search endpoint (with params)."""
    should_filter = _is_json_request(request) or any(
        request.GET.get(param) for param in SEARCH_PARAMS
    )

    if not should_filter:
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
    result = signals.classify_report(report.description) or {}
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


def _log_status_transition(report: Report, from_status: str | None, to_status: str, changed_by=None,
                           note: str = "") -> None:
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


@login_required
def dashboard(request):
    """Post-login landing: admin panel for admins, role-appropriate redirect otherwise."""
    if not _is_admin_user(request.user):
        if user_is_officer(request.user):
            return redirect("officer_panel")
        return redirect("home")

    total_reports = Report.objects.count()
    active_users = User.objects.filter(is_active=True).count()
    resolved_reports = Report.objects.filter(status="resolved").count()
    resolve_rate = round((resolved_reports / total_reports) * 100, 1) if total_reports else 0

    avg_resolution_seconds = (
        Report.objects.filter(status="resolved", status_changed_at__isnull=False)
        .annotate(
            resolution_duration=ExpressionWrapper(
                F("status_changed_at") - F("created_at"),
                output_field=DurationField(),
            )
        )
        .aggregate(avg_duration=Avg("resolution_duration"))
    )
    avg_days = 0
    avg_duration = avg_resolution_seconds.get("avg_duration")
    if avg_duration:
        avg_days = round(avg_duration.total_seconds() / 86400, 1)

    category_counts = list(
        Report.objects.values("category").annotate(total=Count("id")).order_by("category")
    )
    status_counts = list(
        Report.objects.values("status").annotate(total=Count("id")).order_by("status")
    )

    missing_profile_users = User.objects.filter(profile__isnull=True)
    for listed_user in missing_profile_users:
        UserProfile.objects.get_or_create(user=listed_user)

    users = User.objects.select_related("profile").order_by("username")
    categories = ReportCategory.objects.order_by("name")
    sectors = Sector.objects.order_by("name")
    logs = AuditLog.objects.select_related("user").order_by("-timestamp")[:20]

    context = {
        "active_tab": request.GET.get("tab", "analytics"),
        "stats": {
            "total_reports": total_reports,
            "active_users": active_users,
            "resolve_rate": resolve_rate,
            "avg_days": avg_days,
        },
        "category_counts": category_counts,
        "status_counts": status_counts,
        "users": users,
        "categories": categories,
        "sectors": sectors,
        "logs": logs,
        "category_form": ReportCategoryForm(),
        "sector_form": SectorForm(),
        "user_form": AdminUserCreateForm(),
    }
    return render(request, "reports/admin_dashboard.html", context)


@login_required
@_admin_only()
def toggle_user_active(request: HttpRequest, user_id: int) -> HttpResponse:
    """Toggle user active/inactive status from users tab."""
    if request.method != "POST":
        return redirect(f"{reverse('dashboard')}?tab=users")

    user = get_object_or_404(User, id=user_id)
    if user.id == request.user.id:
        messages.error(request, "Не можете да го деактивирате сопствениот профил.")
        return redirect(f"{reverse('dashboard')}?tab=users")

    user.is_active = not user.is_active
    user.save(update_fields=["is_active"])

    _write_audit_log(
        request,
        action="toggle_user_active",
        target_model="User",
        target_id=user.id,
        details={"username": user.username, "is_active": user.is_active},
    )
    state_label = "активиран" if user.is_active else "деактивиран"
    messages.success(request, f"Корисникот {user.username} е {state_label}.")
    return redirect(f"{reverse('dashboard')}?tab=users")


@login_required
@_admin_only()
def create_user(request: HttpRequest) -> HttpResponse:
    """Create a new user from users tab."""
    if request.method == "POST":
        form = AdminUserCreateForm(request.POST)
        if form.is_valid():
            user = User.objects.create_user(
                username=form.cleaned_data["username"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
            )
            role = form.cleaned_data["role"]
            profile, _ = UserProfile.objects.get_or_create(user=user)
            profile.role = role
            profile.save(update_fields=["role"])

            if role == "admin":
                user.is_staff = True
                user.save(update_fields=["is_staff"])

            _write_audit_log(
                request,
                action="create_user",
                target_model="User",
                target_id=user.id,
                details={"username": user.username, "role": role},
            )
            messages.success(request, f"Корисникот {user.username} е успешно додаден.")
        else:
            error_list = []
            for field_name, field_errors in form.errors.items():
                for field_error in field_errors:
                    if field_name == "__all__":
                        error_list.append(str(field_error))
                    else:
                        error_list.append(f"{field_name}: {field_error}")

            error_message = error_list[0] if error_list else "Неуспешно додавање корисник. Проверете ги полињата."
            messages.error(request, error_message)
    return redirect(f"{reverse('dashboard')}?tab=users")


@login_required
@_admin_only()
def delete_user(request: HttpRequest, user_id: int) -> HttpResponse:
    """Delete a user from users tab."""
    if request.method == "POST":
        user = get_object_or_404(User, id=user_id)
        if user.id == request.user.id:
            messages.error(request, "Не можете да се избришете сами себе.")
            return redirect(f"{reverse('dashboard')}?tab=users")

        username = user.username
        user.delete()
        _write_audit_log(
            request,
            action="delete_user",
            target_model="User",
            target_id=user_id,
            details={"username": username},
        )
        messages.success(request, f"Корисникот {username} е избришан.")
    return redirect(f"{reverse('dashboard')}?tab=users")


@login_required
@_admin_only()
def create_category(request: HttpRequest) -> HttpResponse:
    """Create a report category from settings tab."""
    if request.method == "POST":
        payload = request.POST.copy()
        name = (payload.get("name") or "").strip()
        if name and not payload.get("key"):
            payload["key"] = _build_unique_key(ReportCategory, name)

        form = ReportCategoryForm(payload)
        if form.is_valid():
            category = form.save()
            _write_audit_log(
                request,
                action="create_category",
                target_model="ReportCategory",
                target_id=category.id,
                details={"key": category.key, "name": category.name},
            )
            messages.success(request, "Категоријата е успешно додадена.")
        else:
            messages.error(request, "Неуспешно додавање категорија. Проверете ги полињата.")
    return redirect(f"{reverse('dashboard')}?tab=settings")


@login_required
@_admin_only()
def update_category(request: HttpRequest, category_id: int) -> HttpResponse:
    """Update a report category from settings tab."""
    if request.method == "POST":
        category = get_object_or_404(ReportCategory, id=category_id)
        form = ReportCategoryForm(request.POST, instance=category)
        if form.is_valid():
            category = form.save()
            _write_audit_log(
                request,
                action="update_category",
                target_model="ReportCategory",
                target_id=category.id,
                details={"key": category.key, "name": category.name, "is_active": category.is_active},
            )
            messages.success(request, "Категоријата е успешно ажурирана.")
        else:
            messages.error(request, "Неуспешно ажурирање на категоријата.")
    return redirect(f"{reverse('dashboard')}?tab=settings")


@login_required
@_admin_only()
def delete_category(request: HttpRequest, category_id: int) -> HttpResponse:
    """Delete a report category from settings tab."""
    if request.method == "POST":
        category = get_object_or_404(ReportCategory, id=category_id)
        name = category.name
        category.delete()
        _write_audit_log(
            request,
            action="delete_category",
            target_model="ReportCategory",
            target_id=category_id,
            details={"name": name},
        )
        messages.success(request, "Категоријата е избришана.")
    return redirect(f"{reverse('dashboard')}?tab=settings")


@login_required
@_admin_only()
def create_sector(request: HttpRequest) -> HttpResponse:
    """Create a sector from settings tab."""
    if request.method == "POST":
        payload = request.POST.copy()
        name = (payload.get("name") or "").strip()
        if name and not payload.get("key"):
            payload["key"] = _build_unique_key(Sector, name)

        form = SectorForm(payload)
        if form.is_valid():
            sector = form.save()
            _write_audit_log(
                request,
                action="create_sector",
                target_model="Sector",
                target_id=sector.id,
                details={"key": sector.key, "name": sector.name},
            )
            messages.success(request, "Секторот е успешно додаден.")
        else:
            messages.error(request, "Неуспешно додавање сектор. Проверете ги полињата.")
    return redirect(f"{reverse('dashboard')}?tab=settings")


@login_required
@_admin_only()
def update_sector(request: HttpRequest, sector_id: int) -> HttpResponse:
    """Update a sector from settings tab."""
    if request.method == "POST":
        sector = get_object_or_404(Sector, id=sector_id)
        form = SectorForm(request.POST, instance=sector)
        if form.is_valid():
            sector = form.save()
            _write_audit_log(
                request,
                action="update_sector",
                target_model="Sector",
                target_id=sector.id,
                details={"key": sector.key, "name": sector.name, "is_active": sector.is_active},
            )
            messages.success(request, "Секторот е успешно ажуриран.")
        else:
            messages.error(request, "Неуспешно ажурирање на секторот.")
    return redirect(f"{reverse('dashboard')}?tab=settings")


@login_required
@_admin_only()
def delete_sector(request: HttpRequest, sector_id: int) -> HttpResponse:
    """Delete a sector from settings tab."""
    if request.method == "POST":
        sector = get_object_or_404(Sector, id=sector_id)
        name = sector.name
        sector.delete()
        _write_audit_log(
            request,
            action="delete_sector",
            target_model="Sector",
            target_id=sector_id,
            details={"name": name},
        )
        messages.success(request, "Секторот е избришан.")
    return redirect(f"{reverse('dashboard')}?tab=settings")


@login_required
@_admin_only()
def export_reports_csv(request: HttpRequest) -> HttpResponse:
    """Export filtered reports to CSV from dashboard."""
    queryset = _filtered_admin_reports(request)
    
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="reports_export.csv"'
    
    writer = csv.writer(response)
    writer.writerow(REPORT_EXPORT_COLUMNS)
    for report in queryset:
        writer.writerow(_format_report_row(report))
    
    _write_audit_log(
        request,
        action="export_reports_csv",
        target_model="Report",
        target_id=None,
        details={"count": queryset.count(), "filters": request.GET.dict()},
    )
    return response


@login_required
@_admin_only()
def import_reports_stub(request: HttpRequest) -> HttpResponse:
    """Temporary import action endpoint for dashboard UI button."""
    messages.info(request,
                  "Import функцијата е подготвена во UI и ќе биде поврзана со обработка на датотеки во следен task.")
    return redirect(f"{reverse('dashboard')}?tab=analytics")


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

            duplicate = find_potential_duplicate(
                description=report.description,
                latitude=float(report.latitude),
                longitude=float(report.longitude),
            )
            if duplicate is not None:
                report.is_duplicate = True
                report.duplicate_of = duplicate
                messages.warning(
                    request,
                    f"Можно е оваа пријава да е дупликат на пријава #{duplicate.pk}. Ќе биде означена за проверка.",
                )

            if getattr(settings, "AI_CLASSIFICATION_ENABLED", False):
                try:
                    _apply_ai_classification(report)
                except Exception:
                    report.status = "unclassified"
                    report.category = "other"
                    report.priority = "normal"
                    report.sector = "admin"
                    report.ai_processed = False
                    report.status_changed_at = timezone.now()
            else:
                if not report.category:
                    report.category = "other"
                if not report.priority:
                    report.priority = "normal"
                category_to_sector = {
                    "infrastructure": "infrastructure",
                    "utilities": "utilities",
                    "safety": "safety",
                    "health": "health",
                    "other": "admin",
                }
                report.sector = category_to_sector.get(report.category, "admin")

            report.save()
            _log_status_transition(report, None, report.status, changed_by=request.user, note="Креирана пријава")
            send_report_created_email(report)

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
@require_http_methods(["GET", "POST"])
def reports_api(request):
    """GET filtered reports, POST create new report with AI classification."""
    if request.method == "GET" and not _is_json_request(request):
        return redirect("home")
    if request.method == "POST":
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
                    "detail": "Daily limit reached: max 10 reports per 24 hours. Please try again tomorrow.",
                    "limit": MAX_REPORTS_PER_24H,
                    "window_hours": REPORT_WINDOW_HOURS,
                },
                status=429,
            )

        report = Report(
            citizen=request.user,
            description=form.cleaned_data["description"],
            latitude=form.cleaned_data["latitude"],
            longitude=form.cleaned_data["longitude"],
            image=form.cleaned_data.get("image"),
        )
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
    if request.user.is_authenticated:
        base_qs = Report.objects.filter(citizen=request.user)
    else:
        base_qs = Report.objects.none()

    total_count = base_qs.count()
    new_count = base_qs.filter(status="new").count()
    in_progress_count = base_qs.filter(status="in_progress").count()
    done_count = base_qs.filter(status="resolved").count()

    qs = base_qs

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
    send_status_change_email(report)

    return JsonResponse({
        "id": report.pk,
        "status": report.status,
        "internal_note": report.internal_note,
        "status_changed_at": report.status_changed_at.isoformat(),
        "assigned_officer": request.user.username,
    })


@login_required
@require_http_methods(["PATCH"])
def reassign_report(request, report_id):
    """Officer-only endpoint that reassigns a report to a different sector."""
    if not user_is_officer(request.user):
        return JsonResponse({"error": "Only officers may reassign reports."}, status=403)

    report = get_object_or_404(Report, pk=report_id)
    if report.sector != get_user_sector(request.user):
        return JsonResponse({"error": "Officers may only reassign reports in their own sector."}, status=403)

    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON payload."}, status=400)

    sector_id = payload.get("sector_id")
    if not sector_id:
        return JsonResponse({"error": "Missing sector_id."}, status=400)

    try:
        sector = Sector.objects.get(pk=sector_id)
    except Sector.DoesNotExist:
        return JsonResponse({"error": "Invalid sector_id."}, status=400)

    old_sector = report.sector
    report.sector = sector.key
    report.save(update_fields=["sector", "updated_at"])

    # Log the reassignment action
    AuditLog.objects.create(
        user=request.user,
        action="REASSIGN",
        target_model="Report",
        target_id=report.pk,
        details={
            "old_sector": old_sector,
            "new_sector": sector.key,
            "sector_name": sector.name,
        }
    )

    return JsonResponse({
        "id": report.pk,
        "sector": report.sector,
        "sector_name": sector.name,
        "updated_at": report.updated_at.isoformat(),
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


@login_required
def get_sectors_json(request):
    """Return list of active sectors as JSON for frontend dropdowns."""
    if not user_is_officer(request.user):
        return JsonResponse({"error": "Only officers can access this."}, status=403)
    
    sectors = Sector.objects.filter(is_active=True).values('id', 'key', 'name')
    return JsonResponse({
        "sectors": list(sectors)
    })


@login_required
@csrf_exempt
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
        send_report_status_changed_email(report, old_status, report.status)
        send_status_change_email(report)

    payload = _serialize_report(report)
    payload["internal_note"] = report.internal_note
    return JsonResponse(payload)


def user_is_officer(user):
    return _is_officer(user)


def get_user_sector(user):
    profile = UserProfile.objects.filter(user=user).first()
    return profile.sector if profile else None


@login_required
def map_view(request):
    """Render interactive map page with report filters."""
    context = {
        "category_choices": Report.CATEGORY_CHOICES,
        "status_choices": Report.STATUS_CHOICES,
        "sector_choices": Report.SECTOR_CHOICES,
        "priority_choices": Report.PRIORITY_CHOICES,
        "municipality_choices": MUNICIPALITY_CHOICES,
    }
    return render(request, "reports/map.html", context)


@login_required
def reports_json(request):
    """Return reports as JSON for AJAX-based Leaflet map rendering with bounding box filtering."""
    queryset = Report.objects.all().order_by("-created_at")

    # Filter by category, status, municipality
    category = request.GET.get("category", "").strip()
    status = request.GET.get("status", "").strip()
    municipality = request.GET.get("municipality", "").strip()

    if category:
        queryset = queryset.filter(category=category)
    if status:
        queryset = queryset.filter(status=status)
    if municipality:
        queryset = queryset.filter(municipality=municipality)

    # Filter by bounding box (map bounds)
    min_lat = _parse_decimal(request.GET.get("minLat"))
    max_lat = _parse_decimal(request.GET.get("maxLat"))
    min_lng = _parse_decimal(request.GET.get("minLng"))
    max_lng = _parse_decimal(request.GET.get("maxLng"))

    if min_lat is not None and max_lat is not None:
        queryset = queryset.filter(latitude__gte=min_lat, latitude__lte=max_lat)
    if min_lng is not None and max_lng is not None:
        queryset = queryset.filter(longitude__gte=min_lng, longitude__lte=max_lng)

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

    paginator = Paginator(reports, 20)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    return render(request, "reports/officer_panel.html", {
        "reports": page_obj,
        "sector": sector,
    })


@login_required
def search_page(request):
    """Public search page with keyword, filters, list & map toggle."""
    filters = _build_report_filters(request)

    opshtina = request.GET.get("opshtina", "").strip()
    if opshtina:
        filters &= Q(municipality=opshtina)

    queryset = Report.objects.filter(filters).order_by("-created_at")

    sort_by = request.GET.get("sort", "date")
    if sort_by == "priority":
        priority_order = {"urgent": 0, "normal": 1, "low": 2}
        queryset = sorted(queryset, key=lambda r: priority_order.get(r.priority, 99))
    elif sort_by == "status":
        queryset = queryset.order_by("status")
    else:
        queryset = queryset.order_by("-created_at")

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

    paginator = Paginator(queryset, 20)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    context = {
        "reports": page_obj,
        "query": request.GET,
        "status_choices": Report.STATUS_CHOICES,
        "priority_choices": Report.PRIORITY_CHOICES,
        "municipalities": municipalities,
        "total": paginator.count,
    }
    return render(request, "reports/search.html", context)


def my_reports(request):
    if request.user.is_authenticated:
        qs = Report.objects.filter(citizen=request.user)
    else:
        qs = Report.objects.none()

    category = request.GET.get('category', '')
    priority = request.GET.get('priority', '')
    status   = request.GET.get('status', '')

    if category: qs = qs.filter(category=category)
    if priority:  qs = qs.filter(priority=priority)
    if status:    qs = qs.filter(status=status)

    map_pins = json.dumps([
        {'id': r.id, 'lat': float(r.latitude), 'lng': float(r.longitude),
         'category': r.get_category_display(), 'status': r.get_status_display()}
        for r in qs
    ])

    paginator = Paginator(qs, 20)
    page_number = request.GET.get('page', 1)
    try:
        page_obj = paginator.page(page_number)
    except (PageNotAnInteger, EmptyPage):
        page_obj = paginator.page(1)

    return render(request, 'reports/my_reports.html', {
        'reports': page_obj,
        'map_pins': map_pins,
        'category_choices': Report.CATEGORY_CHOICES,
        'priority_choices': Report.PRIORITY_CHOICES,
        'status_choices': Report.STATUS_CHOICES,
        'selected_category': category,
        'selected_priority': priority,
        'selected_status': status,
    })

def new_report(request):
    return render(request, 'reports/my_reports.html')

@login_required
@_admin_only()
def export_reports_excel(request: HttpRequest) -> HttpResponse:
    """Export filtered reports to XLSX from dashboard."""
    if not OPENPYXL_AVAILABLE:
        messages.error(request, "Excel извозот бара openpyxl. Користете CSV извоз.")
        return redirect(f"{reverse('dashboard')}?tab=analytics")

    queryset = _filtered_admin_reports(request)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = "Reports"
    sheet.append(REPORT_EXPORT_COLUMNS)
    for report in queryset:
        sheet.append(_format_report_row(report))

    response = HttpResponse(
        content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    response["Content-Disposition"] = 'attachment; filename="reports_export.xlsx"'
    workbook.save(response)

    _write_audit_log(
        request,
        action="export_reports_excel",
        target_model="Report",
        target_id=None,
        details={"count": queryset.count(), "filters": request.GET.dict()},
    )
    return response


@login_required
@_admin_only()
def delete_report(request: HttpRequest, report_id: int) -> HttpResponse:
    """Soft-delete a report (reversible)."""
    if request.method == "POST":
        report = get_object_or_404(Report.all_objects, pk=report_id)
        report.soft_delete()
        _write_audit_log(
            request,
            action="soft_delete_report",
            target_model="Report",
            target_id=report_id,
            details={"report_id": report_id},
        )
        messages.success(request, f"Пријавата #{report_id} е избришана (може да се врати).")
    return redirect(f"{reverse('dashboard')}?tab=analytics")
