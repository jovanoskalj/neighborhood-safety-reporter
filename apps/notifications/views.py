from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from .models import Notification


@login_required
def notifications_log(request):
    notifications = Notification.objects.order_by("-time")
    return render(request, "reports/notifications_log.html", {"notifications": notifications})