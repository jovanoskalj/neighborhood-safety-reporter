"""Views for account registration, authentication, and profile updates."""

import logging
import random
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import Group, User
from django.core.mail import send_mail
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.utils import timezone
from django.views.decorators.http import require_GET, require_http_methods

from apps.reports.models import MUNICIPALITY_CHOICES, Report

from .forms import LocalizedPasswordChangeForm, ProfileForm, RegisterForm
from .models import AuditLog, EmailVerificationCode, UserNotification, UserProfile

ROLE_GROUPS = {
    "citizen": ["citizen", "citizens"],
    "officer": ["officer", "officers"],
    "admin": ["admin", "administrators"],
}

VERIFICATION_CODE_EXPIRY_MINUTES = 15
logger = logging.getLogger(__name__)


def _is_admin_user(user: User) -> bool:
    if not user.is_authenticated:
        return False
    return user.is_superuser or user.groups.filter(name__in=["admin", "administrators"]).exists()


def _generate_verification_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def _send_verification_code_email(user: User, code: str) -> bool:
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

    try:
        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[user.email],
            html_message=html_message,
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Verification email send failed for user_id=%s email=%s", user.id, user.email)
        return False


def register_view(request):
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

        email_sent = _send_verification_code_email(user, verification_code)
        request.session["pending_verification_user_id"] = user.id

        if email_sent:
            messages.success(request, "Регистрацијата е успешна. Ви испративме 6-цифрен код на вашата е-пошта.")
        else:
            if settings.DEBUG:
                messages.warning(
                    request,
                    f"Регистрацијата е успешна, но email не е испратен. Тест-код за верификација: {verification_code}",
                )
            else:
                messages.warning(request, "Регистрацијата е успешна, но има проблем со праќање email. Обидете се повторно.")
        return redirect("verify_email_code")

    return render(request, "accounts/register.html", {"form": form})


def login_view(request):
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
            profile = UserProfile.objects.filter(user=user).first()
            if profile and profile.must_change_password:
                next_url = "profile"
            elif user.is_superuser:
                next_url = "/dashboard/"
            elif _is_admin_user(user):
                next_url = "/dashboard/?tab=users"
            else:
                next_url = request.GET.get("next") or "my_reports"
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

        dev_code = getattr(settings, "DEV_VERIFICATION_CODE", None)
        if dev_code and code == dev_code:
            verification = None
        else:
            verification = EmailVerificationCode.objects.filter(user=user, code=code).first()

        if dev_code and code == dev_code:
            pass
        elif not verification or verification.is_expired():
            messages.error(request, "Кодот е невалиден или истечен.")
            return redirect("verify_email_code")

        user.is_active = True
        user.save(update_fields=["is_active"])
        if verification:
            verification.delete()
        request.session.pop("pending_verification_user_id", None)
        messages.success(request, "Е-поштата е успешно верификувана. Сега можете да се најавите.")
        return redirect("login")

    return render(request, "accounts/verify_code.html", {"email": user.email})


@login_required
def logout_view(request):
    logout(request)
    return redirect("login")


@login_required
def profile_view(request):
    """Allow users to update basic profile information and passwords."""
    profile, _ = UserProfile.objects.get_or_create(user=request.user)
    is_admin_profile = _is_admin_user(request.user)
    effective_role = "admin" if is_admin_profile else profile.role
    user_reports = Report.objects.filter(citizen=request.user)
    total_reports = user_reports.count()
    resolved_reports = user_reports.filter(status="resolved").count()
    urgent_reports = user_reports.filter(priority="urgent").count()

    distinct_days = {value.date() for value in user_reports.values_list("created_at", flat=True)}

    achievements = [
        {
            "title": "Прва пријава",
            "description": "Поднеси ја првата пријава.",
            "unlocked": total_reports >= 1,
            "progress": min(total_reports, 1),
            "target": 1,
        },
        {
            "title": "Активен граѓанин",
            "description": "Поднеси 5 пријави.",
            "unlocked": total_reports >= 5,
            "progress": min(total_reports, 5),
            "target": 5,
        },
        {
            "title": "Чувар на маало",
            "description": "Поднеси 20 пријави.",
            "unlocked": total_reports >= 20,
            "progress": min(total_reports, 20),
            "target": 20,
        },
        {
            "title": "Решени случаи",
            "description": "Имај 3 решени пријави.",
            "unlocked": resolved_reports >= 3,
            "progress": min(resolved_reports, 3),
            "target": 3,
        },
        {
            "title": "Будно око",
            "description": "Поднеси 3 итни пријави.",
            "unlocked": urgent_reports >= 3,
            "progress": min(urgent_reports, 3),
            "target": 3,
        },
        {
            "title": "Конзистентен корисник",
            "description": "Поднесувај пријави во 3 различни денови.",
            "unlocked": len(distinct_days) >= 3,
            "progress": min(len(distinct_days), 3),
            "target": 3,
        },
    ]

    profile_form = ProfileForm(instance=request.user, prefix="profile")
    password_form = LocalizedPasswordChangeForm(user=request.user, prefix="password")

    if request.method == "POST":
        if "change_password" in request.POST:
            password_form = LocalizedPasswordChangeForm(user=request.user, data=request.POST, prefix="password")
            if password_form.is_valid():
                user = password_form.save()
                profile.must_change_password = False
                profile.save(update_fields=["must_change_password"])
                update_session_auth_hash(request, user)
                messages.success(request, "Лозинката е успешно променета.")
                return redirect("profile")
        else:
            profile_form = ProfileForm(request.POST, instance=request.user, prefix="profile")
            if profile_form.is_valid():
                profile_form.save()
            profile.phone = request.POST.get("phone", profile.phone)
            if request.FILES.get("avatar"):
                profile.avatar = request.FILES["avatar"]
            if profile.role == "officer":
                profile.sector = request.POST.get("sector", profile.sector)
            profile.save()
            messages.success(request, "Профилот е успешно ажуриран.")
            return redirect("profile")

    return render(
        request,
        "accounts/profile.html",
        {
            "profile": profile,
            "role_label": {
                "citizen": "Граѓанин",
                "officer": "Работник",
                "admin": "Администратор",
            }.get(effective_role, effective_role),
            "show_gamification": effective_role == "citizen",
            "sector_choices": UserProfile.SECTOR_CHOICES,
            "total_reports": total_reports,
            "resolved_reports": resolved_reports,
            "achievements": achievements,
            "profile_form": profile_form,
            "password_form": password_form,
        },
    )


@login_required
@user_passes_test(_is_admin_user)
def admin_user_list(request):
    users = User.objects.select_related("profile").all().order_by("id").distinct()
    return render(
        request,
        "accounts/admin_user_list.html",
        {
            "users": users,
            "role_choices": UserProfile.ROLE_CHOICES,
            "sector_choices": UserProfile.SECTOR_CHOICES,
            "municipality_choices": MUNICIPALITY_CHOICES,
        },
    )


@login_required
@user_passes_test(_is_admin_user)
def admin_user_toggle(request, user_id):
    if request.method == "POST":
        target_user = User.objects.get(id=user_id)
        target_user.is_active = not target_user.is_active
        target_user.save()
        AuditLog.objects.create(
            user=request.user,
            action="toggle_active",
            target_model="User",
            target_id=user_id,
            details={"is_active": target_user.is_active},
        )
        messages.success(request, f"User {target_user.username} updated.")
        return redirect("admin_user_list")


@login_required
@user_passes_test(_is_admin_user)
def admin_user_update_role(request, user_id):
    if request.method == "POST":
        target_user = User.objects.get(id=user_id)
        profile, _ = UserProfile.objects.get_or_create(user=target_user)
        new_role = request.POST.get("role")
        if new_role in dict(UserProfile.ROLE_CHOICES):
            profile.role = new_role
            profile.sector = request.POST.get("sector", "") if new_role == "officer" else ""
            profile.municipality = request.POST.get("municipality", "") if new_role == "officer" else ""
            profile.save(update_fields=["role", "sector", "municipality"])
            target_user.is_staff = new_role == "admin" or target_user.is_superuser
            target_user.save(update_fields=["is_staff"])
            AuditLog.objects.create(
                user=request.user,
                action="update_role",
                target_model="User",
                target_id=user_id,
                details={"new_role": new_role, "sector": profile.sector, "municipality": profile.municipality},
            )
            messages.success(request, f"Role updated to {new_role}.")
        return redirect("admin_user_list")


@staff_member_required
def admin_system_log(request):
    logs = AuditLog.objects.select_related("user").order_by("-timestamp")[:200]
    return render(request, "accounts/admin_system_log.html", {"logs": logs})


@staff_member_required
def admin_category_list(request):
    categories = Report.CATEGORY_CHOICES
    sectors = Report.SECTOR_CHOICES
    return render(
        request,
        "accounts/admin_categories.html",
        {"categories": categories, "sectors": sectors},
    )


# User notification views
@login_required
def notifications_list(request):
    """Display all notifications for the current user."""
    notifications = UserNotification.objects.filter(user=request.user).order_by("-created_at")

    notification_type = request.GET.get("type")
    if notification_type:
        notifications = notifications.filter(type=notification_type)

    read_status = request.GET.get("read")
    if read_status == "read":
        notifications = notifications.filter(is_read=True)
    elif read_status == "unread":
        notifications = notifications.filter(is_read=False)

    return render(
        request,
        "accounts/notifications_list.html",
        {
            "notifications": notifications,
            "notification_type": notification_type,
            "read_status": read_status,
        },
    )


@login_required
@require_GET
def notifications_summary(request):
    """Return lightweight notification data for the navbar poller."""
    unread_count = UserNotification.objects.filter(user=request.user, is_read=False).count()
    recent_notifications = UserNotification.objects.filter(user=request.user).order_by("-created_at")[:5]
    return JsonResponse(
        {
            "unread_count": unread_count,
            "recent": [
                {
                    "id": notification.id,
                    "title": notification.title,
                    "message": notification.message,
                    "is_read": notification.is_read,
                    "report_id": notification.report_id,
                    "created_at": notification.created_at.strftime("%H:%M"),
                }
                for notification in recent_notifications
            ],
        }
    )


@login_required
@require_http_methods(["POST"])
def mark_notification_read(request, notification_id):
    """Mark a specific notification as read."""
    notification = get_object_or_404(UserNotification, pk=notification_id, user=request.user)
    notification.is_read = True
    notification.save(update_fields=["is_read"])

    if request.headers.get("Accept", "").startswith("application/json"):
        return JsonResponse({"success": True})

    return redirect("notifications_list")


@login_required
@require_http_methods(["POST"])
def mark_all_notifications_read(request):
    """Mark all notifications for the user as read."""
    UserNotification.objects.filter(user=request.user, is_read=False).update(is_read=True)

    if request.headers.get("Accept", "").startswith("application/json"):
        return JsonResponse({"success": True})

    return redirect("notifications_list")


@login_required
@require_http_methods(["POST"])
def delete_notification(request, notification_id):
    """Delete a specific notification."""
    notification = get_object_or_404(UserNotification, pk=notification_id, user=request.user)
    notification.delete()

    if request.headers.get("Accept", "").startswith("application/json"):
        return JsonResponse({"success": True})

    return redirect("notifications_list")
