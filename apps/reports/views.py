import csv
import io
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render, redirect
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
    return render(request, "reports/submit_report.html")

@login_required
def export_reports(request):
    try:
        profile = request.user.userprofile
        if profile.role != 'admin' and not request.user.is_superuser:
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