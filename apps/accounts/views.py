from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import Group
from .forms import RegisterForm
from .models import UserProfile
from verify_email.email_handler import ActivationMailManager

def register_view(request):
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.is_active = False
            user.save()

            role = form.cleaned_data.get('role')
            sector = form.cleaned_data.get('sector')
            phone = form.cleaned_data.get('phone')

            UserProfile.objects.create(user=user, role=role, sector=sector, phone=phone)

            group, _ = Group.objects.get_or_create(name=role)
            user.groups.add(group)

            # django-verify-email
            # ActivationMailManager.send_verification_link(
            #     request, form, active_after_verification=True
            # )
            ActivationMailManager.send_verification_link(request, form)


            return redirect('login')
    else:
        form = RegisterForm()
    return render(request, "accounts/register.html", {"form": form})

def login_view(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user:
            login(request, user)
            return redirect('home')
        else:
            return render(request, "accounts/login.html", {"error": "Invalid credentials"})
    return render(request, "accounts/login.html")

def logout_view(request):
    logout(request)
    return redirect('login')