from django import forms

from .models import Report


class ReportSubmissionForm(forms.ModelForm):
    """Citizen-facing report submission form with GPS + image validation."""

    municipality = forms.ChoiceField(
        choices=[
            ("", "Избери општина"),
            ("centar", "Центар"),
            ("karpos", "Карпош"),
            ("aerodrom", "Аеродром"),
            ("kisela_voda", "Кисела Вода"),
            ("gazi_baba", "Гази Баба"),
            ("butel", "Бутел"),
        ],
        required=False,
        label="Општина",
    )

    class Meta:
        model = Report
        fields = ["description", "latitude", "longitude", "image"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5, "placeholder": "Опишете го проблемот..."}),
            "latitude": forms.NumberInput(attrs={"step": "0.000001", "placeholder": "41.9981"}),
            "longitude": forms.NumberInput(attrs={"step": "0.000001", "placeholder": "21.4254"}),
            "image": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png"}),
        }
        labels = {
            "description": "Опис",
            "latitude": "Географска ширина (Lat)",
            "longitude": "Географска должина (Lng)",
            "image": "Слика (JPG/PNG)",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field_name, field in self.fields.items():
            css = "form-control"
            if field_name == "image":
                css = "form-control"
            elif isinstance(field.widget, forms.Select):
                css = "form-select"
            field.widget.attrs["class"] = css

    def clean_latitude(self):
        latitude = self.cleaned_data["latitude"]
        if latitude < -90 or latitude > 90:
            raise forms.ValidationError("Latitude must be between -90 and 90.")
        return latitude

    def clean_longitude(self):
        longitude = self.cleaned_data["longitude"]
        if longitude < -180 or longitude > 180:
            raise forms.ValidationError("Longitude must be between -180 and 180.")
        return longitude

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            return image

        content_type = getattr(image, "content_type", "")
        valid_types = {"image/jpeg", "image/png"}
        if content_type and content_type not in valid_types:
            raise forms.ValidationError("Only JPG and PNG images are allowed.")

        max_size_mb = 5
        if image.size > max_size_mb * 1024 * 1024:
            raise forms.ValidationError("Image size must be up to 5MB.")

        return image


class ReportStatusUpdateForm(forms.ModelForm):
    """Officer form for status updates + internal notes."""

    class Meta:
        model = Report
        fields = ["status", "internal_note"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "internal_note": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }
