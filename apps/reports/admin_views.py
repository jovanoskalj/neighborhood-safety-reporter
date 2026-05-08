"""Admin dashboard views: dashboard summary, user/category/sector CRUD,
report import/export, and admin-only classification/duplicate review.

These views never call functions that tests patch via `apps.reports.views.X`,
so it's safe to host them in their own module.
"""
import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from apps.accounts.models import AuditLog, UserProfile
from apps.accounts.utils import notify_report_classified

from ._view_helpers import (
    OPENPYXL_AVAILABLE,
    REPORT_EXPORT_COLUMNS,
    _admin_only,
    _build_unique_key,
    _filtered_admin_reports,
    _format_report_row,
    _import_reports_from_rows,
    _is_admin_user,
    _is_officer,
    _read_import_rows,
    _write_audit_log,
)
from .forms import (
    AdminUserCreateForm,
    AdminUserUpdateForm,
    ReportCategoryForm,
    ReportSubmissionForm,  # noqa: F401  imported for backwards-compat with old views.py
    SectorForm,
)
from .models import MUNICIPALITY_CHOICES, Report, ReportCategory, Sector

if OPENPYXL_AVAILABLE:
    import openpyxl


@login_required
def dashboard(request):
    """Post-login landing: admin panel for admins, role-appropriate redirect otherwise."""
    if not _is_admin_user(request.user):
        if _is_officer(request.user):
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
    priority_counts = list(
        Report.objects.values("priority").annotate(total=Count("id")).order_by("priority")
    )
    sector_counts = list(
        Report.objects.values("sector").annotate(total=Count("id")).order_by("sector")
    )

    missing_profile_users = User.objects.filter(profile__isnull=True)
    for listed_user in missing_profile_users:
        UserProfile.objects.get_or_create(user=listed_user)

    users_queryset = User.objects.select_related("profile").order_by("username")
    role_filter = request.GET.get("role", "")
    valid_roles = {value for value, _ in UserProfile.ROLE_CHOICES}
    if role_filter not in valid_roles:
        role_filter = ""
    users = users_queryset.filter(profile__role=role_filter) if role_filter else users_queryset
    role_filter_cards = [
        {"value": "", "label": "Сите", "count": users_queryset.count()},
        {
            "value": "citizen",
            "label": "Граѓани",
            "count": users_queryset.filter(profile__role="citizen").count(),
        },
        {
            "value": "officer",
            "label": "Работници",
            "count": users_queryset.filter(profile__role="officer").count(),
        },
        {
            "value": "admin",
            "label": "Админи",
            "count": users_queryset.filter(profile__role="admin").count(),
        },
    ]
    categories = ReportCategory.objects.order_by("name")
    sectors = Sector.objects.order_by("name")
    logs = AuditLog.objects.select_related("user").order_by("-timestamp")[:20]

    unclassified_reports = Report.objects.filter(
        Q(category="other") | Q(status="unclassified")
    ).select_related("citizen").order_by("-created_at")[:50]

    pending_duplicate_reports = (
        Report.objects.filter(duplicate_verdict="pending")
        .exclude(duplicate_of__isnull=True)
        .select_related("citizen", "duplicate_of")
        .order_by("-created_at")[:100]
    )
    pending_duplicate_count = Report.objects.filter(duplicate_verdict="pending").exclude(duplicate_of__isnull=True).count()

    # For classification form: exclude "Друго" (other) — it's the unclassified marker.
    active_categories_for_classification = list(
        ReportCategory.objects.filter(is_active=True).exclude(key="other").values_list('key', 'name')
    )
    bulk_municipality = request.GET.get("bulk_municipality", "")
    bulk_sector = request.GET.get("bulk_sector", "")
    bulk_queryset = Report.objects.filter(status="resolved").exclude(citizen__email="")
    if bulk_municipality:
        bulk_queryset = bulk_queryset.filter(municipality=bulk_municipality)
    if bulk_sector:
        bulk_queryset = bulk_queryset.filter(sector=bulk_sector)
    default_bulk_subject = "Известување од Безбеден Град"
    default_bulk_message = (
        "Почитувани,\n\n"
        "Ве информираме дека пријавите што одговараат на избраните филтри се обработени. "
        "Ви благодариме што придонесувате за побезбедна заедница.\n\n"
        "Со почит,\nТимот на Безбеден Град"
    )

    context = {
        "active_tab": request.GET.get("tab", "users"),
        "stats": {
            "total_reports": total_reports,
            "active_users": active_users,
            "resolve_rate": resolve_rate,
            "avg_days": avg_days,
            "open_reports": Report.objects.exclude(status__in=["resolved", "rejected", "withdrawn"]).count(),
            "high_priority_reports": Report.objects.filter(priority="urgent").count(),
            "unclassified_reports": Report.objects.filter(Q(category="other") | Q(status="unclassified")).count(),
        },
        "category_counts": category_counts,
        "status_counts": status_counts,
        "priority_counts": priority_counts,
        "sector_counts": sector_counts,
        "users": users,
        "selected_user_role": role_filter,
        "role_filter_cards": role_filter_cards,
        "categories": categories,
        "sectors": sectors,
        "logs": logs,
        "unclassified_reports": unclassified_reports,
        "unclassified_count": Report.objects.filter(Q(category="other") | Q(status="unclassified")).count(),
        "pending_duplicate_reports": pending_duplicate_reports,
        "pending_duplicate_count": pending_duplicate_count,
        "category_form": ReportCategoryForm(),
        "sector_form": SectorForm(),
        "user_form": AdminUserCreateForm(),
        "role_choices": AdminUserCreateForm.ROLE_CHOICES,
        "sector_choices": list(Sector.objects.filter(is_active=True).values_list('key', 'name')),
        "category_choices": active_categories_for_classification,
        "status_choices": Report.STATUS_CHOICES,
        "priority_choices": Report.PRIORITY_CHOICES,
        "municipality_choices": MUNICIPALITY_CHOICES,
        "export_columns": REPORT_EXPORT_COLUMNS,
        "bulk_count": bulk_queryset.count(),
        "bulk_municipality": bulk_municipality,
        "bulk_sector": bulk_sector,
        "default_bulk_subject": default_bulk_subject,
        "default_bulk_message": default_bulk_message,
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
            profile.sector = form.cleaned_data.get("sector") if role == "officer" else ""
            profile.municipality = form.cleaned_data.get("municipality") if role == "officer" else ""
            profile.must_change_password = True
            profile.save(update_fields=["role", "sector", "municipality", "must_change_password"])

            if role == "admin":
                user.is_staff = True
                user.save(update_fields=["is_staff"])

            _write_audit_log(
                request,
                action="create_user",
                target_model="User",
                target_id=user.id,
                details={
                    "username": user.username,
                    "role": role,
                    "sector": profile.sector,
                    "municipality": profile.municipality,
                    "must_change_password": True,
                },
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
def update_user(request: HttpRequest, user_id: int) -> HttpResponse:
    """Update a user's role and worker assignment from the users tab."""
    if request.method != "POST":
        return redirect(f"{reverse('dashboard')}?tab=users")

    user = get_object_or_404(User, id=user_id)
    profile, _ = UserProfile.objects.get_or_create(user=user)
    form = AdminUserUpdateForm(request.POST)

    if form.is_valid():
        role = form.cleaned_data["role"]
        profile.role = role
        profile.sector = form.cleaned_data.get("sector") if role == "officer" else ""
        profile.municipality = form.cleaned_data.get("municipality") if role == "officer" else ""
        profile.save(update_fields=["role", "sector", "municipality"])

        user.is_staff = role == "admin" or user.is_superuser
        user.save(update_fields=["is_staff"])

        _write_audit_log(
            request,
            action="update_user_assignment",
            target_model="User",
            target_id=user.id,
            details={
                "username": user.username,
                "role": role,
                "sector": profile.sector,
                "municipality": profile.municipality,
            },
        )
        messages.success(request, f"Корисникот {user.username} е ажуриран.")
    else:
        first_error = next(iter(form.errors.values()))[0] if form.errors else "Неуспешно ажурирање."
        messages.error(request, first_error)

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
        if "is_active" not in payload:
            payload["is_active"] = "true"

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
            state_label = "видлив" if sector.is_active else "скриен"
            messages.success(request, f"Секторот „{sector.name}“ сега е {state_label}.")
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
def import_reports(request: HttpRequest) -> HttpResponse:
    """Validate and import CSV/XLSX rows from dashboard."""
    if request.method != "POST":
        return redirect(f"{reverse('dashboard')}?tab=analytics")

    uploaded_file = request.FILES.get("file")
    if not uploaded_file:
        messages.error(request, "Изберете CSV или XLSX датотека за импорт.")
        return redirect(f"{reverse('dashboard')}?tab=analytics")

    try:
        rows = _read_import_rows(uploaded_file)
        inserted, skipped_duplicates, invalid_rows = _import_reports_from_rows(rows, request.user)
    except ValueError as exc:
        messages.error(request, str(exc))
        return redirect(f"{reverse('dashboard')}?tab=analytics")

    if inserted:
        messages.success(request, f"Импортирани се {inserted} валидни пријави.")
    if skipped_duplicates:
        preview = ", ".join(skipped_duplicates[:8])
        extra = "..." if len(skipped_duplicates) > 8 else ""
        messages.warning(request, f"Прескокнати дупликат ID: {preview}{extra}")
    if invalid_rows:
        preview = "; ".join(f"ред {item['row']}: {item['reason']}" for item in invalid_rows[:8])
        extra = " ..." if len(invalid_rows) > 8 else ""
        messages.error(request, f"Невалидни редови: {preview}{extra}")
    if not inserted and not skipped_duplicates and not invalid_rows:
        messages.info(request, "Датотеката не содржи редови за импорт.")

    _write_audit_log(
        request,
        action="import_reports",
        target_model="Report",
        target_id=None,
        details={
            "inserted": inserted,
            "duplicates": len(skipped_duplicates),
            "invalid": len(invalid_rows),
            "filename": uploaded_file.name,
        },
    )
    return redirect(f"{reverse('dashboard')}?tab=analytics")


@login_required
@_admin_only()
@require_http_methods(["POST"])
def admin_classify_report(request, report_id: int):
    """Admin endpoint to classify unclassified reports."""
    report = get_object_or_404(Report, pk=report_id)

    category = (request.POST.get("category") or "").strip()
    priority = (request.POST.get("priority") or "").strip()
    sector = (request.POST.get("sector") or "").strip()

    valid_categories = {value for value, _ in Report.CATEGORY_CHOICES}
    valid_priorities = {value for value, _ in Report.PRIORITY_CHOICES}
    valid_sectors = {value for value, _ in Report.SECTOR_CHOICES}

    errors = {}
    if category and category not in valid_categories:
        errors["category"] = "Invalid category"
    if priority and priority not in valid_priorities:
        errors["priority"] = "Invalid priority"
    if sector and sector not in valid_sectors:
        errors["sector"] = "Invalid sector"

    if errors:
        return JsonResponse({"errors": errors}, status=400)

    update_fields = []
    old_category = report.category
    old_priority = report.priority
    old_sector = report.sector

    if category and category != "other":
        report.category = category
        update_fields.append("category")

    if priority:
        report.priority = priority
        update_fields.append("priority")

    if sector:
        report.sector = sector
        update_fields.append("sector")

    if category and category != "other" and report.status == "unclassified":
        report.status = "new"
        update_fields.append("status")

    if update_fields:
        report.save(update_fields=update_fields)
        _write_audit_log(
            request,
            action="classify_report",
            target_model="Report",
            target_id=report.id,
            details={
                "old_category": old_category,
                "new_category": report.category,
                "old_priority": old_priority,
                "new_priority": report.priority,
                "old_sector": old_sector,
                "new_sector": report.sector,
            },
        )
        notify_report_classified(report, classified_by=request.user)
        messages.success(request, "Извештајот е успешно класифициран.")

    return redirect(f"{reverse('dashboard')}?tab=unclassified")


@login_required
@_admin_only()
@require_http_methods(["POST"])
def review_duplicate_report(request, report_id: int):
    """Admin confirms or rejects automatic duplicate suggestion."""
    report = get_object_or_404(Report, pk=report_id)
    if report.duplicate_verdict != "pending":
        messages.error(request, "Оваа пријава не е во редица за преглед на дупликат.")
        return redirect(f"{reverse('dashboard')}?tab=duplicates")

    action = (request.POST.get("action") or "").strip()
    if action == "confirm":
        report.duplicate_verdict = "confirmed"
        report.is_duplicate = True
        report.save(update_fields=["duplicate_verdict", "is_duplicate", "updated_at"])
        _write_audit_log(
            request,
            action="duplicate_verdict_confirm",
            target_model="Report",
            target_id=report.id,
            details={
                "duplicate_of_id": report.duplicate_of_id,
            },
        )
        messages.success(
            request,
            f"ПРЈ-{report.id} е означена како дупликат на ПРЈ-{report.duplicate_of_id}.",
        )
    elif action == "reject":
        old_dup_id = report.duplicate_of_id
        report.duplicate_verdict = "rejected"
        report.is_duplicate = False
        report.duplicate_of = None
        report.save(update_fields=["duplicate_verdict", "is_duplicate", "duplicate_of", "updated_at"])
        _write_audit_log(
            request,
            action="duplicate_verdict_reject",
            target_model="Report",
            target_id=report.id,
            details={"previous_duplicate_of_id": old_dup_id},
        )
        messages.success(
            request,
            f"ПРЈ-{report.id} е задржана како посебна пријава (не е дупликат).",
        )
    else:
        messages.error(request, "Непозната акција.")

    return redirect(f"{reverse('dashboard')}?tab=duplicates")
