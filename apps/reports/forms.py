"""Forms for report submission (web + API) and admin dashboard CRUD."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django import forms
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as CoreValidationError

from .models import MUNICIPALITY_CHOICES, Report, ReportCategory, Sector


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
    image = forms.ImageField(required=False)

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
        self.fields["municipality"].required = False

    def clean_image(self):
        """Reject uploads outside the allowed JPG/PNG MIME types (FR-08)."""
        image = self.cleaned_data.get("image")
        if not image:
            return image
        content_type = getattr(image, "content_type", "") or ""
        if content_type not in {"image/jpeg", "image/png"}:
            raise forms.ValidationError("Дозволени се само JPG или PNG слики.")
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


class ReportCategoryForm(forms.ModelForm):
    """Form for creating and updating report categories from admin panel."""

    class Meta:
        model = ReportCategory
        fields = ["key", "name", "is_active"]


class SectorForm(forms.ModelForm):
    """Form for creating and updating sectors from admin panel."""

    is_active = forms.BooleanField(required=False, widget=forms.CheckboxInput)

    class Meta:
        model = Sector
        fields = ["key", "name", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure is_active is properly set from POST data
        if self.instance.pk and not self.data:
            self.fields['is_active'].initial = self.instance.is_active


class AdminUserCreateForm(forms.Form):
    """Form for creating users from admin dashboard users tab."""

    ROLE_CHOICES = [
        ("citizen", "Граѓанин"),
        ("officer", "Работник"),
        ("admin", "Админ"),
    ]

    username = forms.CharField(max_length=150, required=False)
    email = forms.EmailField()
    password = forms.CharField(max_length=128, widget=forms.PasswordInput)
    role = forms.ChoiceField(choices=ROLE_CHOICES)
    sector = forms.ChoiceField(required=False)
    municipality = forms.ChoiceField(choices=[("", "---------")] + list(MUNICIPALITY_CHOICES), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically populate sector choices from active sectors
        active_sectors = Sector.objects.filter(is_active=True).values_list('key', 'name')
        self.fields['sector'].choices = [("", "---------")] + list(active_sectors)

    def clean_username(self) -> str:
        username = (self.cleaned_data.get("username") or "").strip()
        if username and User.objects.filter(username=username).exists():
            raise forms.ValidationError("Корисничкото име веќе постои.")
        return username

    def clean_email(self) -> str:
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Е-поштата веќе постои.")
        return email

    def clean_password(self) -> str:
        """Enforce Django's configured password validators (min length, etc.)."""
        password = self.cleaned_data.get("password", "")
        try:
            validate_password(password)
        except CoreValidationError as error:
            raise forms.ValidationError(list(error.messages))
        return password

    def clean(self):
        cleaned_data = super().clean()
        username = cleaned_data.get("username")
        email = cleaned_data.get("email")
        if not username and email:
            base_username = email.split("@", 1)[0] or "user"
            username = base_username
            counter = 2
            while User.objects.filter(username=username).exists():
                username = f"{base_username}{counter}"
                counter += 1
            cleaned_data["username"] = username
        elif not username:
            self.add_error("username", "Внесете корисничко име или е-пошта.")

        if cleaned_data.get("role") == "officer":
            if not cleaned_data.get("sector"):
                self.add_error("sector", "Изберете сектор за работникот.")
            if not cleaned_data.get("municipality"):
                self.add_error("municipality", "Изберете општина за работникот.")
        return cleaned_data


class AdminUserUpdateForm(forms.Form):
    """Form for immediate admin updates to role and worker assignment."""

    ROLE_CHOICES = AdminUserCreateForm.ROLE_CHOICES

    role = forms.ChoiceField(choices=ROLE_CHOICES)
    sector = forms.ChoiceField(required=False)
    municipality = forms.ChoiceField(choices=[("", "---------")] + list(MUNICIPALITY_CHOICES), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Dynamically populate sector choices from active sectors
        active_sectors = Sector.objects.filter(is_active=True).values_list('key', 'name')
        self.fields['sector'].choices = [("", "---------")] + list(active_sectors)

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get("role") == "officer":
            if not cleaned_data.get("sector"):
                self.add_error("sector", "Изберете сектор за работникот.")
            if not cleaned_data.get("municipality"):
                self.add_error("municipality", "Изберете општина за работникот.")
        return cleaned_data
