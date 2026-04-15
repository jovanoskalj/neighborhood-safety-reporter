from django import forms
from django.contrib.auth.models import User

from .models import ReportCategory, Sector


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
