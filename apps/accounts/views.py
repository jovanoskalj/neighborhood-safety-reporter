"""Views for account registration, authentication, and profile updates."""

import random
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from .forms import RegisterForm
from .models import EmailVerificationCode, UserProfile


ROLE_GROUPS = {
    "citizen": ["citizen", "citizens"],
    "officer": ["officer", "officers"],
    "admin": ["admin", "administrators"],
}

VERIFICATION_CODE_EXPIRY_MINUTES = 15


def _generate_verification_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def _send_verification_code_email(user: User, code: str) -> None:
    subject = "Email Verification Code"
    context = {
        "inactive_user": user,
        "verification_code": code,
        "expiry_minutes": VERIFICATION_CODE_EXPIRY_MINUTES,
    }
    html_message = render_to_string("accounts/verification_email.html", context)
    plain_message = (
        f"Здраво {user.username},\n\n"
        f"Вашиот код за потврда е: {code}\n"
        f"Кодот важи {VERIFICATION_CODE_EXPIRY_MINUTES} минути."
    )

    send_mail(
        subject=subject,
        message=plain_message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[user.email],
        html_message=html_message,
        fail_silently=False,
    )


def register_view(request):
    """Register a citizen user and send email verification."""
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save(commit=False)
        user.is_active = False
        user.email = form.cleaned_data["email"]
        user.save()

        role = "citizen"
        sector = ""
        phone = form.cleaned_data.get("phone", "")

        profile, _ = UserProfile.objects.get_or_create(user=user)
        profile.role = role
        profile.sector = sector
        profile.phone = phone
        profile.save()

        for group_name in ROLE_GROUPS.get(role, [role]):
            group, _ = Group.objects.get_or_create(name=group_name)
            user.groups.add(group)

        verification_code = _generate_verification_code()
        EmailVerificationCode.objects.update_or_create(
            user=user,
            defaults={
                "code": verification_code,
                "expires_at": timezone.now() + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES),
            },
        )

        _send_verification_code_email(user, verification_code)
        request.session["pending_verification_user_id"] = user.id

        messages.success(request, "Регистрацијата е успешна. Ви испративме 6-цифрен код на вашата е-пошта.")
        return redirect("verify_email_code")

    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    """Authenticate user with Django session auth."""
    if request.method == "POST":
        username = request.POST.get("username", "")
        password = request.POST.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            next_url = request.GET.get("next") or "dashboard"
            return redirect(next_url)
        else:
            inactive_user = User.objects.filter(username=username, is_active=False).first()
            if inactive_user and inactive_user.check_password(password):
                messages.error(request, "Профилот сѐ уште не е верификуван. Проверете ја вашата е-пошта.")
                return render(request, "accounts/login.html", status=200)
            messages.error(request, "Невалидни податоци за најава.")
            return render(request, "accounts/login.html", status=200)
    return render(request, "accounts/login.html")


def verify_email_code_view(request):
    """Verify newly registered account using a 6-digit code sent by email."""
    pending_user_id = request.session.get("pending_verification_user_id")
    if not pending_user_id:
        messages.info(request, "Нема активна верификација. Ве молиме регистрирајте се.")
        return redirect("register")

    user = User.objects.filter(id=pending_user_id, is_active=False).first()
    if not user:
        request.session.pop("pending_verification_user_id", None)
        messages.info(request, "Профилот е веќе верификуван. Најавете се.")
        return redirect("login")

    if request.method == "POST":
        code = (request.POST.get("code") or "").strip()
        if not code.isdigit() or len(code) != 6:
            messages.error(request, "Кодот мора да има точно 6 цифри.")
            return redirect("verify_email_code")

        verification = EmailVerificationCode.objects.filter(user=user, code=code).first()
        if not verification or verification.is_expired():
            messages.error(request, "Кодот е невалиден или истечен.")
            return redirect("verify_email_code")

        user.is_active = True
        user.save(update_fields=["is_active"])
        verification.delete()
        request.session.pop("pending_verification_user_id", None)
        messages.success(request, "Е-поштата е успешно верификувана. Сега можете да се најавите.")
        return redirect("login")

    return render(request, "accounts/verify_code.html", {"email": user.email})


@login_required
def logout_view(request):
    """Log out current user and redirect to login page."""
    logout(request)
    return redirect("login")


@login_required
def profile_view(request):
    """Allow users to update basic profile information."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)

    if request.method == "POST":
        profile.phone = request.POST.get("phone", profile.phone)
        role = profile.role
        if role == "officer":
            profile.sector = request.POST.get("sector", profile.sector)
        profile.save()
        messages.success(request, "Профилот е успешно ажуриран.")
        return redirect("profile")

    return render(request, "accounts/profile.html", {"profile": profile, "sector_choices": UserProfile.SECTOR_CHOICES})