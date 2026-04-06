from django.shortcuts import redirect

class RoleRequiredMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path.startswith('/officer/') and not request.user.groups.filter(name='officer').exists():
            return redirect('login')

        if request.path.startswith('/admin/') and not request.user.groups.filter(name='admin').exists():
            return redirect('login')

        return self.get_response(request)
