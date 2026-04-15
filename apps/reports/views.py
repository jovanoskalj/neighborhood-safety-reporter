import json
import logging

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from apps.ai_classifier.classifier import classify_report
from apps.reports.forms import ReportCreateForm
from apps.reports.models import Report

logger = logging.getLogger(__name__)


def _normalize_classification(classification):
	if not isinstance(classification, dict):
		raise ValueError("Classification response must be an object")

	category = str(classification.get("category", "")).strip().lower()
	priority = str(classification.get("priority", "")).strip().lower()
	sector = str(classification.get("sector", "")).strip().lower()

	valid_categories = {choice[0] for choice in Report.CATEGORY_CHOICES}
	valid_priorities = {choice[0] for choice in Report.PRIORITY_CHOICES}
	valid_sectors = {choice[0] for choice in Report.SECTOR_CHOICES}

	if category not in valid_categories:
		raise ValueError(f"Invalid category returned by classifier: {category}")
	if priority not in valid_priorities:
		raise ValueError(f"Invalid priority returned by classifier: {priority}")
	if sector not in valid_sectors:
		raise ValueError(f"Invalid sector returned by classifier: {sector}")

	return {
		"category": category,
		"priority": priority,
		"sector": sector,
	}


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

	report = Report.objects.create(
		citizen=request.user,
		description=form.cleaned_data["description"],
		latitude=form.cleaned_data["latitude"],
		longitude=form.cleaned_data["longitude"],
		image=form.cleaned_data.get("image"),
		status="new",
	)

	try:
		raw_classification = classify_report({"description": report.description})
		classification = _normalize_classification(raw_classification)

		report.category = classification["category"]
		report.priority = classification["priority"]
		report.sector = classification["sector"]
		report.status = "new"
		report.ai_processed = True
	except Exception:
		logger.exception("AI classification failed for report id=%s", report.id)
		report.status = "unclassified"
		report.ai_processed = False

	report.save(update_fields=["category", "priority", "sector", "status", "ai_processed", "updated_at"])

	return JsonResponse(_serialize_report(report), status=201)
