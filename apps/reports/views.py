import json
from django.shortcuts import render
from .models import Report

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