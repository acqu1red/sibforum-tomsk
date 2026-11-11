from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode

from forums.security import check_registration_rate_limit, client_ip
from registrations.selection import RegistrationError
from .models import Admin2FAProfile


class Admin2FAMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if self.is_admin_path(request.path) and not self.admin_host_allowed(request):
            if request.path.startswith('/api/v1/admin'):
                return JsonResponse({'ok': False, 'error': 'not_found'}, status=404)
            raise Http404
        if request.path == '/admin/login/' and request.method == 'POST':
            try:
                check_registration_rate_limit(client_ip(request), 'admin_login')
            except RegistrationError as error:
                return HttpResponse(error.message, status=error.status, content_type='text/plain; charset=utf-8')
        if request.user.is_authenticated and request.user.is_staff and self.requires_verification(request):
            if request.path.startswith('/api/v1/admin/'):
                return JsonResponse({'ok': False, 'error': 'two_factor_required'}, status=401)
            profile = Admin2FAProfile.objects.filter(user=request.user).first()
            view = 'two-factor-verify' if profile and profile.confirmed_at else 'two-factor-setup'
            return redirect(reverse(view) + '?' + urlencode({'next': request.get_full_path()}))
        return self.get_response(request)

    @staticmethod
    def is_admin_path(path):
        return path == '/admin' or path.startswith('/admin/') or path == '/api/v1/admin' or path.startswith('/api/v1/admin/')

    @staticmethod
    def admin_host_allowed(request):
        host = request.get_host().split(':')[0].lower().rstrip('.')
        return host in settings.ADMIN_HOSTS

    @staticmethod
    def requires_verification(request):
        if not settings.ADMIN_TOTP_REQUIRED:
            return False
        path = request.path
        if not Admin2FAMiddleware.is_admin_path(path):
            return False
        if path.startswith('/admin/login/') or path.startswith('/admin/logout/') or path.startswith('/admin/2fa/'):
            return False
        return not (
            request.session.get('admin_2fa_verified') is True
            and request.session.get('admin_2fa_user_id') == request.user.id
        )
