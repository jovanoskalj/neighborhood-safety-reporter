"""Forms for report submission (web + API) and admin dashboard CRUD."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as CoreValidationError

from .models import Report, ReportCategory, Sector


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


class ReportCreateForm(forms.Form):
    """JSON/multipart form for the REST-style ``create_report`` endpoint."""

    description = forms.CharField(required=True)
    latitude = _CoordinateField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = _CoordinateField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)
    image = forms.ImageField(required=False)

    def clean_description(self):
        description = self.cleaned_data["description"].strip()
        if not description:
            raise forms.ValidationError("Description cannot be empty.")
        return description


class ReportSubmissionForm(forms.ModelForm):
    """Validates citizen-submitted report fields from the web form.

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
        self.fields["municipality"].required = False

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if not image:
            return image

        if image.size > 5 * 1024 * 1024:
            raise forms.ValidationError("Сликата не смее да биде поголема од 5MB.")

        content_type = getattr(image, "content_type", "") or ""
        if content_type not in {"image/jpeg", "image/png"}:
            raise forms.ValidationError("Дозволени се само JPG или PNG слики.")

        try:
            from PIL import Image
            img = Image.open(image)
            img.verify()
            if img.format not in {"JPEG", "PNG"}:
                raise forms.ValidationError("Датотеката не е валидна JPG или PNG слика.")
            image.seek(0)
        except Exception:
            raise forms.ValidationError("Датотеката не е валидна слика.")

        return image


class ReportCategoryForm(forms.ModelForm):
    """Form for creating and updating report categories from admin panel."""

    class Meta:
        model = ReportCategory
        fields = ["key", "name", "is_active"]


class SectorForm(forms.ModelForm):
    """Form for creating and updating sectors from admin panel."""

    class Meta:
        model = Sector
        fields = ["key", "name", "is_active"]


class AdminUserCreateForm(forms.Form):
    """Form for creating users from admin dashboard users tab."""

    ROLE_CHOICES = [
        ("citizen", "Граѓанин"),
        ("officer", "Работник"),
        ("admin", "Админ"),
    ]

    username = forms.CharField(max_length=150)
    email = forms.EmailField(required=False)
    password = forms.CharField(max_length=128, widget=forms.PasswordInput)
    role = forms.ChoiceField(choices=ROLE_CHOICES)

    def clean_username(self) -> str:
        username = self.cleaned_data["username"].strip()
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("Корисничкото име веќе постои.")
        return username

    def clean_password(self) -> str:
        """Enforce Django's configured password validators (min length, etc.)."""
        password = self.cleaned_data.get("password", "")
        try:
            validate_password(password)
        except CoreValidationError as error:
            raise forms.ValidationError(list(error.messages))
        return password
