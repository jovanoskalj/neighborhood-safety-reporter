from django import forms
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User


class ProfileForm(forms.ModelForm):
    """Allow users to edit basic account information."""

    email = forms.EmailField(required=True)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "first_name": "Име",
            "last_name": "Презиме",
            "email": "Е-пошта",
        }
        placeholders = {
            "first_name": "",
            "last_name": "",
            "email": "",
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
        email = (self.cleaned_data.get("email") or "").strip().lower()
        current_email = (self.instance.email or "").strip().lower()

        if not email:
            raise forms.ValidationError("Е-пошта е задолжителна.")

        if email == current_email:
            return email

        duplicate = User.objects.filter(email__iexact=email).exclude(pk=self.instance.pk)
        if duplicate.exists():
            raise forms.ValidationError("Веќе постои корисник со оваа е-пошта.")
        return email


class LocalizedPasswordChangeForm(PasswordChangeForm):
    """Password form with localized labels and Bootstrap classes."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["old_password"].label = "Тековна лозинка"
        self.fields["new_password1"].label = "Нова лозинка"
        self.fields["new_password2"].label = "Потврди нова лозинка"
        self.fields["new_password1"].help_text = "Лозинката треба да биде доволно силна и различна од лични податоци."
        for field in self.fields.values():
            field.widget.attrs.update({"class": "form-control", "placeholder": "••••••••"})

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
