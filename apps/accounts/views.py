"""Views for account registration, authentication, and profile updates."""

import random
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.models import User
from django.contrib.auth.models import Group
from django.contrib.auth.decorators import login_required
from django.core.mail import send_mail
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.utils import timezone

from .forms import LocalizedPasswordChangeForm, ProfileForm, RegisterForm
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

        if settings.SENDGRID_ENABLED:
            verification_code = _generate_verification_code()
        else:
            verification_code = str(settings.DEV_VERIFICATION_CODE)

        EmailVerificationCode.objects.update_or_create(
            user=user,
            defaults={
                "code": verification_code,
                "expires_at": timezone.now() + timedelta(minutes=VERIFICATION_CODE_EXPIRY_MINUTES),
            },
        )

        if settings.SENDGRID_ENABLED:
            _send_verification_code_email(user, verification_code)
        request.session["pending_verification_user_id"] = user.id

        if settings.SENDGRID_ENABLED:
            messages.success(request, "Регистрацијата е успешна. Ви испративме 6-цифрен код на вашата е-пошта.")
        else:
            messages.success(request, f"Регистрацијата е успешна. Тест-кодот за верификација е: {verification_code}")
        return redirect("verify_email_code")

    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
    """Authenticate user with Django session auth."""
    if request.method == "POST":
        identifier = (request.POST.get("username") or "").strip()
        password = request.POST.get("password", "")
        user = authenticate(request, username=identifier, password=password)

        # Support email-based login in the same input field.
        if not user and identifier:
            email_matches = User.objects.filter(email__iexact=identifier)
            for email_user in email_matches:
                user = authenticate(request, username=email_user.username, password=password)
                if user:
                    break

        if user:
            login(request, user)
            next_url = request.GET.get("next") or "dashboard"
            return redirect(next_url)
        else:
            inactive_user = User.objects.filter(username=identifier, is_active=False).first()
            if not inactive_user:
                inactive_user = User.objects.filter(email__iexact=identifier, is_active=False).first()
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

        if not settings.SENDGRID_ENABLED:
            if code != str(settings.DEV_VERIFICATION_CODE):
                messages.error(request, "Кодот е невалиден или истечен.")
                return redirect("verify_email_code")

            user.is_active = True
            user.save(update_fields=["is_active"])
            EmailVerificationCode.objects.filter(user=user).delete()
            request.session.pop("pending_verification_user_id", None)
            messages.success(request, "Е-поштата е успешно верификувана. Сега можете да се најавите.")
            return redirect("login")

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
    """Allow users to edit profile info and update account password."""
    profile_form = ProfileForm(instance=request.user, prefix="profile")
    password_form = LocalizedPasswordChangeForm(user=request.user, prefix="password")

    if request.method == "POST":
        if "save_profile" in request.POST:
            profile_form = ProfileForm(request.POST, instance=request.user, prefix="profile")
            if profile_form.is_valid():
                profile_form.save()
                messages.success(request, "Профилот е успешно ажуриран.")
                return redirect("profile")
        elif "change_password" in request.POST:
            password_form = LocalizedPasswordChangeForm(user=request.user, data=request.POST, prefix="password")
            if password_form.is_valid():
                user = password_form.save()
                update_session_auth_hash(request, user)
                messages.success(request, "Лозинката е успешно променета.")
                return redirect("profile")

    return render(
        request,
        "accounts/profile.html",
        {
            "profile_form": profile_form,
            "password_form": password_form,
        },
    )