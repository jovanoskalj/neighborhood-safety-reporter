"""Forms for report submission (web + API) and admin dashboard CRUD."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as CoreValidationError

from .models import Report, ReportCategory, Sector
from .validators import validate_image_content


_COORD_QUANTUM = Decimal("0.000001")


class _CoordinateField(forms.DecimalField):
    """DecimalField that quantizes inputs to the model's precision."""

    def to_python(self, value):
        value = super().to_python(value)
        if value is None:
            return value
        try:
            return value.quantize(_COORD_QUANTUM, rounding=ROUND_HALF_UP)
        except InvalidOperation:
            return value


class ReportCreateForm(forms.Form):
    """JSON/multipart form for the REST-style ``reports_api`` endpoint."""

    description = forms.CharField(required=True)
    latitude = _CoordinateField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = _CoordinateField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)
    image = forms.ImageField(required=False, validators=[validate_image_content])

    def clean_description(self):
        description = self.cleaned_data["description"].strip()
        if not description:
            raise forms.ValidationError("Description cannot be empty.")
        return description


class ReportSubmissionForm(forms.ModelForm):
    """Validates citizen-submitted report fields from the web form."""

    latitude = _CoordinateField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
    longitude = _CoordinateField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)

    class Meta:
        model = Report
        fields = [
            "description",
            "municipality",
            "latitude",
            "longitude",
            "image",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "image": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png"}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields["municipality"].required = True


class ReportStatusUpdateForm(forms.ModelForm):
    """Officer form for status updates + internal notes."""

    class Meta:
        model = Report
        fields = ["status", "internal_note"]
        widgets = {
            "status": forms.Select(attrs={"class": "form-select"}),
            "internal_note": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }


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
