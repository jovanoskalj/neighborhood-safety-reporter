from ast import keyword
import csv
import io
import json
from datetime import date
from decimal import Decimal, InvalidOperation

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.core.paginator import EmptyPage, PageNotAnInteger, Paginator
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import Round
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from urllib3 import request

from apps.accounts.models import AuditLog, UserProfile
from apps.notifications.senders import send_status_change_email

from .duplicate_detection import find_potential_duplicate
from .forms import (
    AdminUserCreateForm,
    ReportCategoryForm,
    ReportCreateForm,
    ReportSubmissionForm,
    SectorForm,
)
from .models import MUNICIPALITY_CHOICES, Report, ReportCategory, Sector


SEARCH_PARAMS = (
    "category", "status", "sector", "priority",
    "from", "to", "keyword",
    "lat_min", "lat_max", "lng_min", "lng_max",
    "page",
)


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
    return render(request, "reports/dashboard.html", context)


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
    """Export current reports to CSV from dashboard."""
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="reports_export.csv"'

    writer = csv.writer(response)
    writer.writerow(["id", "citizen", "category", "sector", "status", "priority", "created_at"])
    for report in Report.objects.select_related("citizen").order_by("-created_at"):
        writer.writerow(
            [
                report.id,
                report.citizen.username,
                report.category,
                report.sector,
                report.status,
                report.priority,
                report.created_at.isoformat(),
            ]
        )

    _write_audit_log(
        request,
        action="export_reports_csv",
        target_model="Report",
        target_id=None,
        details={"count": Report.objects.count()},
    )
    return response


@login_required
@_admin_only()
def import_reports_stub(request: HttpRequest) -> HttpResponse:
    """Temporary import action endpoint for dashboard UI button."""
    messages.info(request, "Import функцијата е подготвена во UI и ќе биде поврзана со обработка на датотеки во следен task.")
    return redirect(f"{reverse('dashboard')}?tab=analytics")


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
            try:
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

                # Set sector based on category if AI classification might fail
                category_to_sector = {
                    'infrastructure': 'infrastructure',
                    'utilities': 'utilities', 
                    'safety': 'safety',
                    'health': 'health',
                    'other': 'admin'  # Default to admin for 'other' category
                }
                report.sector = category_to_sector.get(report.category, 'admin')
                
                report.save()
                # Always show success message, regardless of AI classification
                if duplicate is None:
                    messages.success(request, "Вашата пријава е успешно поднесена.")
                return redirect("submit_report")
            except Exception as e:
                messages.error(request, f"Грешка при зачувување: {str(e)}")
        else:
            # Form is invalid - add error message and show form with errors
            messages.error(request, "Ве молиме поправете ги грешките во формата.")
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
    send_status_change_email(report)

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

    duplicate = find_potential_duplicate(
        description=form.cleaned_data["description"],
        latitude=float(form.cleaned_data["latitude"]),
        longitude=float(form.cleaned_data["longitude"]),
    )
    if duplicate is not None:
        return JsonResponse(
            {
                "detail": "Duplicate report detected.",
                "duplicate_of_id": duplicate.pk,
            },
            status=409,
        )
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


@login_required
def search_page(request):
    """Public search page with keyword, filters, list & map toggle."""
    filters = _build_report_filters(request)
    
  
    opshtina = request.GET.get("opshtina", "").strip()
    if opshtina:
        filters &= Q(municipality=opshtina)
    
    queryset = Report.objects.filter(filters).order_by("-created_at")
    
    # Sorting
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

    context = {
        "reports": queryset,
        "query": request.GET,
        "status_choices": Report.STATUS_CHOICES,
        "priority_choices": Report.PRIORITY_CHOICES,
        "municipalities": municipalities,
        "total": len(queryset) if isinstance(queryset, list) else queryset.count(),
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
        {
            'id':       r.id,
            'lat':      float(r.latitude),
            'lng':      float(r.longitude),
            'category': r.get_category_display(),
            'status':   r.get_status_display(),
        }
        for r in qs
    ])

    return render(request, 'reports/my_reports.html', {
        'reports':           qs,
        'map_pins':          map_pins,
        'category_choices':  Report.CATEGORY_CHOICES,
        'priority_choices':  Report.PRIORITY_CHOICES,
        'status_choices':    Report.STATUS_CHOICES,
        'selected_category': category,
        'selected_priority': priority,
        'selected_status':   status,
    })

def new_report(request):
    return render(request, 'reports/my_reports.html')

@login_required
def export_reports(request):
    try:
        profile = request.user.userprofile
        if profile.role != 'admin':
             return redirect('dashboard')
    except:
        return redirect('dashboard')
    fmt = request.GET.get('format', 'csv')
    date_from = request.GET.get('from')
    date_to = request.GET.get('to')
    category = request.GET.get('category')
    status = request.GET.get('status')

    reports = Report.objects.all().order_by('-created_at')

    if date_from:
        reports = reports.filter(created_at__date__gte=date_from)
    if date_to:
        reports = reports.filter(created_at__date__lte=date_to)
    if category:
        reports = reports.filter(category=category)
    if status:
        reports = reports.filter(status=status)

    headers = ['ID', 'Description', 'Category', 'Priority', 'Status', 'Sector', 'Latitude', 'Longitude', 'Created At']

    def get_row(r):
        return [r.id, r.description, r.category, r.priority, r.status, r.sector, r.latitude, r.longitude, r.created_at.strftime('%Y-%m-%d %H:%M')]

    if fmt == 'excel' and OPENPYXL_AVAILABLE:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = 'Reports'
        ws.append(headers)
        for r in reports:
            ws.append(get_row(r))
        output = io.BytesIO()
        wb.save(output)
        output.seek(0)
        response = HttpResponse(output.read(), content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="reports.xlsx"'
        return response

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="reports.csv"'
    writer = csv.writer(response)
    writer.writerow(headers)
    for r in reports:
        writer.writerow(get_row(r))
    return response
