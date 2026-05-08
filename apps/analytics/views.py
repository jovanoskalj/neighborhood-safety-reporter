from django.contrib.auth.decorators import user_passes_test
from django.contrib.auth.models import User
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.db.models.functions import TruncMonth, TruncWeek, TruncYear
from django.http import JsonResponse
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_GET

from apps.reports.models import Report

_TRUNC_MAP = {
    "weekly": TruncWeek,
    "monthly": TruncMonth,
    "yearly": TruncYear,
}
_DEFAULT_PERIOD = "monthly"


def is_analytics_user(user) -> bool:
    """Return True if user is an officer or administrator."""
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name__in=['admin', 'administrators', 'officer', 'officers']).exists()


def _filtered_reports(request):
    queryset = Report.objects.all()
    for param in ("category", "status", "sector", "priority", "municipality"):
        value = (request.GET.get(param) or "").strip().lower()
        if value:
            queryset = queryset.filter(**{param: value})

    from_date = parse_date((request.GET.get("from") or "").strip())
    to_date = parse_date((request.GET.get("to") or "").strip())
    if from_date:
        queryset = queryset.filter(created_at__date__gte=from_date)
    if to_date:
        queryset = queryset.filter(created_at__date__lte=to_date)
    return queryset


def _group_by_field(queryset, field):
    """Return [{label, count}] for a Report CharField using a single query."""
    return [
        {"label": row[field], "count": row["count"]}
        for row in queryset.values(field).annotate(count=Count("id")).order_by(field)
    ]


def _time_series(queryset, period):
    """Return chronological [{period, count}] bucketed by the requested period."""
    trunc_fn = _TRUNC_MAP.get(period, _TRUNC_MAP[_DEFAULT_PERIOD])
    qs = (
        queryset.annotate(period=trunc_fn("created_at"))
        .values("period")
        .annotate(count=Count("id"))
        .order_by("period")
    )
    return [
        {"period": row["period"].isoformat() if row["period"] else None, "count": row["count"]}
        for row in qs
    ]


@require_GET
@user_passes_test(is_analytics_user)
def stats(request) -> JsonResponse:
    """Provide aggregated statistics for dashboard visualization."""
    raw_period = (request.GET.get("period") or "").strip().lower()
    period = raw_period if raw_period in _TRUNC_MAP else _DEFAULT_PERIOD
    queryset = _filtered_reports(request)

    data = {
        "total": queryset.count(),
        "by_category": _group_by_field(queryset, "category"),
        "by_status": _group_by_field(queryset, "status"),
        "by_priority": _group_by_field(queryset, "priority"),
        "by_sector": _group_by_field(queryset, "sector"),
        "by_municipality": _group_by_field(queryset, "municipality"),
        "by_period": {
            "period_type": period,
            "data": _time_series(queryset, period),
        },
    }

    return JsonResponse(data)


@require_GET
@user_passes_test(is_analytics_user)
def kpi_metrics(request) -> JsonResponse:
    """Provide KPI metrics (total reports, active users, resolution rate, avg time) based on filters."""
    queryset = _filtered_reports(request)

    total_reports = queryset.count()
    resolved_reports = queryset.filter(status="resolved").count()
    open_reports = queryset.exclude(status__in=["resolved", "rejected", "withdrawn"]).count()
    high_priority_reports = queryset.filter(priority="urgent").count()
    unclassified_reports = queryset.filter(Q(category="other") | Q(status="unclassified")).count()
    resolve_rate = round((resolved_reports / total_reports) * 100, 1) if total_reports else 0

    # Calculate average resolution time
    avg_resolution_data = (
        queryset.filter(status="resolved", status_changed_at__isnull=False)
        .annotate(
            resolution_duration=ExpressionWrapper(
                F("status_changed_at") - F("created_at"),
                output_field=DurationField(),
            )
        )
        .aggregate(avg_duration=Avg("resolution_duration"))
    )
    avg_days = 0
    avg_duration = avg_resolution_data.get("avg_duration")
    if avg_duration:
        avg_days = round(avg_duration.total_seconds() / 86400, 1)

    # Get active users count (globally, not filtered)
    active_users = User.objects.filter(is_active=True).count()

    return JsonResponse({
        "total_reports": total_reports,
        "active_users": active_users,
        "resolve_rate": resolve_rate,
        "avg_days": avg_days,
        "open_reports": open_reports,
        "high_priority_reports": high_priority_reports,
        "unclassified_reports": unclassified_reports,
    })
