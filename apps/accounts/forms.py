from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

class RegisterForm(UserCreationForm):
    """Public registration form. Citizens only."""

    email = forms.EmailField(required=True)
    phone = forms.CharField(required=False)

    class Meta:
        model = User
        fields = ["username", "email", "password1", "password2", "phone"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "username": "Корисничко име",
            "email": "Е-пошта",
            "phone": "Телефон",
            "password1": "Лозинка",
            "password2": "Потврди лозинка",
        }
        placeholders = {
            "username": "",
            "email": "",
            "phone": "+389 7x xxx xxx",
            "password1": "••••••••",
            "password2": "••••••••",
        }
        for name, field in self.fields.items():
            field.label = labels.get(name, field.label)
            field.widget.attrs.update(
                {
                    "class": "form-control",
                    "placeholder": placeholders.get(name, ""),
                }
            )

    def clean_email(self):
        """Ensure one account per email to avoid token ambiguity."""
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Profile with this email already exists. Please log in.")
        return email

    def clean(self):
        """Default clean hook for future validations."""
        return super().clean()
