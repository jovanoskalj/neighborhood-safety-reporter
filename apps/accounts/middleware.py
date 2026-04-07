from django.shortcuts import redirect


class RoleRequiredMiddleware:
    """Simple path-based role protection for officer/admin sections."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user

        if request.path.startswith('/officer/'):
            if not user.is_authenticated or not user.groups.filter(name__in=['officer', 'officers']).exists():
                return redirect('login')

        if request.path.startswith('/management/'):
            if not user.is_authenticated or not (
                user.groups.filter(name__in=['admin', 'administrators']).exists() or user.is_superuser
            ):
                return redirect('login')

        return self.get_response(request)
