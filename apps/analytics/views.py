from django.contrib.auth.decorators import user_passes_test
from django.db.models import Count
from django.db.models.functions import TruncMonth, TruncWeek, TruncYear
from django.http import JsonResponse
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


def _group_by_field(field):
    """Return [{label, count}] for a Report CharField using a single query."""
    return [
        {"label": row[field], "count": row["count"]}
        for row in Report.objects.values(field).annotate(count=Count("id")).order_by(field)
    ]


def _time_series(period):
    """Return chronological [{period, count}] bucketed by the requested period."""
    trunc_fn = _TRUNC_MAP.get(period, _TRUNC_MAP[_DEFAULT_PERIOD])
    qs = (
        Report.objects.annotate(period=trunc_fn("created_at"))
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

    data = {
        "total": Report.objects.count(),
        "by_category": _group_by_field("category"),
        "by_status": _group_by_field("status"),
        "by_priority": _group_by_field("priority"),
        "by_period": {
            "period_type": period,
            "data": _time_series(period),
        },
    }

    return JsonResponse(data)
