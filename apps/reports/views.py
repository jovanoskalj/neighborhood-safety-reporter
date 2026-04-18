from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.http import JsonResponse
from django.db.models import Count
from .models import Report


def home(request):
    """Render project landing page."""
    return render(request, "reports/home.html")


def dashboard(request):
    """Render post-login dashboard page."""
    return render(request, "reports/dashboard.html")


@login_required
def submit_report(request):
    """Render report submission page (login required)."""
    return render(request, "reports/submit_report.html")

def heatmap(request):
    """Returns lat/lng/weight data for Leaflet.heat heatmap plugin."""
    data = Report.objects.filter(
        latitude__isnull=False,
        longitude__isnull=False
    ).values('latitude', 'longitude').annotate(weight=Count('id'))

    result = [
        {
            'lat': float(item['latitude']),
            'lng': float(item['longitude']),
            'weight': item['weight']
        }
        for item in data
    ]

    return JsonResponse(result, safe=False)