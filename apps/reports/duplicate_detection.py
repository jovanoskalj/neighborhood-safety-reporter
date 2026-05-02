"""Duplicate report detection helpers.

We don't have GIS-backed queries in this project, so we approximate a radius
search with a bounding box filter and then apply an exact haversine check.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Optional, Tuple

from django.db.models import QuerySet
from django.utils import timezone

from .models import Report


@dataclass(frozen=True)
class DuplicateDetectionConfig:
    radius_meters: float = 50.0
    lookback_days: int = 365
    similarity_threshold: float = 0.82
    max_candidates: int = 200


def _haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bounding_box(lat: float, lng: float, radius_m: float) -> Tuple[float, float, float, float]:
    # ~111_320 meters per latitude degree.
    lat_delta = radius_m / 111_320.0
    cos_lat = math.cos(math.radians(lat))
    lng_delta = radius_m / (111_320.0 * max(cos_lat, 1e-6))
    return (lat - lat_delta, lat + lat_delta, lng - lng_delta, lng + lng_delta)


def _normalize_text(value: str) -> str:
    return " ".join((value or "").lower().split())


def _levenshtein_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)

    # Ensure we keep the smaller string as the inner dimension.
    if len(a) < len(b):
        a, b = b, a

    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, start=1):
        current = [i]
        for j, cb in enumerate(b, start=1):
            insert_cost = current[j - 1] + 1
            delete_cost = previous[j] + 1
            replace_cost = previous[j - 1] + (0 if ca == cb else 1)
            current.append(min(insert_cost, delete_cost, replace_cost))
        previous = current
    return previous[-1]


def _similarity_ratio(a: str, b: str) -> float:
    a_norm = _normalize_text(a)
    b_norm = _normalize_text(b)
    if not a_norm and not b_norm:
        return 1.0
    if not a_norm or not b_norm:
        return 0.0
    dist = _levenshtein_distance(a_norm, b_norm)
    denom = max(len(a_norm), len(b_norm))
    return 1.0 - (dist / denom)


def find_potential_duplicate(
    *,
    description: str,
    latitude: float,
    longitude: float,
    config: DuplicateDetectionConfig = DuplicateDetectionConfig(),
    base_queryset: Optional[QuerySet] = None,
) -> Optional[Report]:
    qs = base_queryset if base_queryset is not None else Report.objects.all()

    min_lat, max_lat, min_lng, max_lng = _bounding_box(latitude, longitude, config.radius_meters)
    cutoff = None
    if config.lookback_days and config.lookback_days > 0:
        cutoff = timezone.now() - timedelta(days=config.lookback_days)

    candidates = (
        (qs.filter(created_at__gte=cutoff) if cutoff is not None else qs)
        .filter(latitude__gte=min_lat, latitude__lte=max_lat, longitude__gte=min_lng, longitude__lte=max_lng)
        .order_by("-created_at")[: config.max_candidates]
    )

    best: Optional[Tuple[Report, float, float]] = None  # (report, distance_m, similarity)
    for report in candidates:
        dist = _haversine_m(latitude, longitude, float(report.latitude), float(report.longitude))
        if dist > config.radius_meters:
            continue
        similarity = _similarity_ratio(description, report.description)
        if similarity < config.similarity_threshold:
            continue
        if best is None or dist < best[1]:
            best = (report, dist, similarity)

    return best[0] if best else None

