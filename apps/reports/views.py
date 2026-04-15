import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.text import slugify
from django.urls import reverse

from apps.accounts.models import AuditLog, UserProfile

from .forms import AdminUserCreateForm, ReportCategoryForm, SectorForm
from .models import Report, ReportCategory, Sector


def home(request):
    """Render project landing page."""
    return render(request, "reports/home.html")


def _is_admin_user(user: User) -> bool:
    """Allow dashboard access to superusers and admin group users."""
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name__in=["admin", "administrators"]).exists()


def _admin_only() -> callable:
    """Decorator for admin-only endpoints."""
    return user_passes_test(_is_admin_user)


def _write_audit_log(request: HttpRequest, action: str, target_model: str, target_id: int | None, details: dict) -> None:
    """Persist admin action to system log."""
    AuditLog.objects.create(
        user=request.user,
        action=action,
        target_model=target_model,
        target_id=target_id,
        details=details,
    )


def _build_unique_key(model: type[ReportCategory] | type[Sector], raw_name: str) -> str:
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
@_admin_only()
def dashboard(request):
    """Render admin dashboard with analytics, users, settings, and logs."""
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

    missing_profile_users = User.objects.filter(userprofile__isnull=True)
    for listed_user in missing_profile_users:
        UserProfile.objects.get_or_create(user=listed_user)

    users = User.objects.select_related("userprofile").order_by("username")
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
    """Render report submission page (login required)."""
    return render(request, "reports/submit_report.html")