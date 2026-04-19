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
from django.contrib.admin.views.decorators import staff_member_required
from apps.reports.models import Report

from .forms import RegisterForm
from .models import EmailVerificationCode, UserProfile, AuditLog


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


@staff_member_required
def admin_user_list(request):
    """List all users with their roles and active status."""
    users = User.objects.select_related('userprofile').all().order_by('id').distinct()
    return render(request, 'accounts/admin_user_list.html', {'users': users})


@staff_member_required
def admin_user_toggle(request, user_id):
    """Activate or deactivate a user account."""
    if request.method == 'POST':
        target_user = User.objects.get(id=user_id)
        target_user.is_active = not target_user.is_active
        target_user.save()
        AuditLog.objects.create(
            user=request.user,
            action='toggle_active',
            target_model='User',
            target_id=user_id,
            details={'is_active': target_user.is_active}
        )
        messages.success(request, f"User {target_user.username} updated.")
        return redirect('admin_user_list')
    

@staff_member_required
def admin_user_update_role(request, user_id):
    """Update a user's role."""
    if request.method == 'POST':
        target_user = User.objects.get(id=user_id)
        profile, _ = UserProfile.objects.get_or_create(user=target_user)
        new_role = request.POST.get('role')
        if new_role in dict(UserProfile.ROLE_CHOICES):
            UserProfile.objects.filter(user=target_user).update(role=new_role)
            AuditLog.objects.create(
                user=request.user,
                action='update_role',
                target_model='User',
                target_id=user_id,
                details={'new_role': new_role}
            )
            messages.success(request, f"Role updated to {new_role}.")
        return redirect('admin_user_list')
    

@staff_member_required
def admin_system_log(request):
    """Read-only view of all audit log entries."""
    logs = AuditLog.objects.select_related('user').order_by('-timestamp')[:200]
    return render(request, 'accounts/admin_system_log.html', {'logs': logs})

@staff_member_required
def admin_category_list(request):
    """List available report categories and sectors."""
    categories = Report.CATEGORY_CHOICES
    sectors = Report.SECTOR_CHOICES
    return render(request, 'accounts/admin_categories.html', {
        'categories': categories,
        'sectors': sectors
    })