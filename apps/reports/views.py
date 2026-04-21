import json
import csv
import io
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render, redirect
from django.utils import timezone
from django.views.decorators.http import require_http_methods
from django.http import HttpResponse
from .models import Report

try:
    import openpyxl
    OPENPYXL_AVAILABLE = True
except ImportError:
    OPENPYXL_AVAILABLE = False

    
def home(request):
    return render(request, "reports/home.html")


def dashboard(request):
    return render(request, "reports/dashboard.html")


@login_required
def submit_report(request):
    """Render report submission page (login required)."""
    return render(request, "reports/submit_report.html")


@login_required
def map_view(request):
    """Render interactive map page with report filters."""
    municipalities = (
        Report.objects.exclude(municipality="")
        .values_list("municipality", flat=True)
        .distinct()
        .order_by("municipality")
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

def user_is_officer(user):
    if not user.is_authenticated:
        return False
    if not hasattr(user, "userprofile"):
        return False
    return user.userprofile.role == "officer"


# def get_user_sector(user):
#     if hasattr(user, 'profile'):
#         return getattr(user.profile, 'sector', None)
#     return None

def get_user_sector(user):
    if hasattr(user, 'userprofile'):
        return getattr(user.userprofile, 'sector', None)
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

    return render(request, "reports/submit_report.html")

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
