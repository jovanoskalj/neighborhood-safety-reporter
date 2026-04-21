from django import forms


class ReportCreateForm(forms.Form):
    description = forms.CharField(required=True)
    latitude = forms.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = forms.DecimalField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)
    image = forms.ImageField(required=False)

    def clean_description(self):
        description = self.cleaned_data["description"].strip()
        if not description:
            raise forms.ValidationError("Description cannot be empty.")
        return description
"""Forms for citizen-facing report submission."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import forms

from .models import Report


_COORD_QUANTUM = Decimal("0.000001")


class _CoordinateField(forms.DecimalField):
    """DecimalField that transparently quantizes to the model's precision.

    Leaflet's map-click handler hands back full-float-precision lat/lng
    values (~14 decimal places). The ``Report`` model stores coordinates
    with ``decimal_places=6``, so the default ``DecimalField`` validator
    would reject that input. Quantizing in ``to_python`` normalizes the
    value before any validator runs.
    """

    def to_python(self, value):
        value = super().to_python(value)
        if value is None:
            return value
        try:
            return value.quantize(_COORD_QUANTUM, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return value


class ReportSubmissionForm(forms.ModelForm):
    """Validates citizen-submitted report fields before persistence.

    ``citizen``, ``status``, ``sector`` and AI-driven fields are set
    server-side (by the view and the AI classifier pipeline), so they
    are intentionally excluded from the client-facing form.
    """

    latitude = _CoordinateField(max_digits=9, decimal_places=6)
    longitude = _CoordinateField(max_digits=9, decimal_places=6)

    class Meta:
        model = Report
        fields = [
            "description",
            "category",
            "priority",
            "municipality",
            "latitude",
            "longitude",
            "image",
        ]

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["municipality"].required = True

    def clean_image(self):
        """Reject uploads outside the allowed JPG/PNG MIME types (FR-08)."""
        image = self.cleaned_data.get("image")
        if not image:
            return image
        content_type = getattr(image, "content_type", "") or ""
        if content_type not in {"image/jpeg", "image/png"}:
            raise forms.ValidationError("Дозволени се само JPG или PNG слики.")
        return image
