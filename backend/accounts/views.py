import time
from urllib.parse import quote, urlencode

from django.contrib.admin.views.decorators import staff_member_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme

from .forms import TwoFactorCodeForm
from .models import Admin2FAProfile
from .totp import verify_totp


def next_url(request):
    candidate = request.POST.get('next') or request.GET.get('next') or '/admin/'
    if url_has_allowed_host_and_scheme(candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return candidate
    return '/admin/'


def mark_success(request):
    request.session['admin_2fa_verified'] = True
    request.session['admin_2fa_user_id'] = request.user.id
    request.session.pop('admin_2fa_attempts', None)
    request.session.pop('admin_2fa_locked_until', None)


def mark_invalid(request, form):
    if time.time() < request.session.get('admin_2fa_locked_until', 0):
        form.add_error('code', 'Слишком много попыток. Повторите через несколько минут.')
        return
    attempts = request.session.get('admin_2fa_attempts', 0) + 1
    request.session['admin_2fa_attempts'] = attempts
    if attempts >= 5:
        request.session['admin_2fa_attempts'] = 0
        request.session['admin_2fa_locked_until'] = time.time() + 300
        form.add_error('code', 'Слишком много попыток. Повторите через 5 минут.')
    else:
        form.add_error('code', f'Неверный код. Осталось попыток: {5 - attempts}.')


@staff_member_required
def setup(request):
    profile, _ = Admin2FAProfile.objects.get_or_create(user=request.user)
    if profile.confirmed_at:
        return redirect('two-factor-verify')
    secret = profile.get_or_create_secret()
    form = TwoFactorCodeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        counter = verify_totp(secret, form.cleaned_data['code'], profile.last_counter)
        if counter is not None:
            profile.confirmed_at = timezone.now()
            profile.last_counter = counter
            profile.save(update_fields=('confirmed_at', 'last_counter', 'updated_at'))
            mark_success(request)
            return redirect(next_url(request))
        mark_invalid(request, form)
    uri = 'otpauth://totp/' + quote('SiberianForum:' + request.user.get_username()) + '?' + urlencode({
        'secret': secret,
        'issuer': 'SiberianForum',
        'algorithm': 'SHA1',
        'digits': 6,
        'period': 30,
    })
    return render(request, 'accounts/two_factor.html', {
        'form': form,
        'is_setup': True,
        'secret': secret,
        'otpauth_uri': uri,
        'next': next_url(request),
        'title': 'Настройка двухфакторной защиты',
    })


@staff_member_required
def verify(request):
    profile, _ = Admin2FAProfile.objects.get_or_create(user=request.user)
    if not profile.confirmed_at:
        return redirect('two-factor-setup')
    form = TwoFactorCodeForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        counter = verify_totp(profile.get_or_create_secret(), form.cleaned_data['code'], profile.last_counter)
        if counter is not None:
            profile.last_counter = counter
            profile.save(update_fields=('last_counter', 'updated_at'))
            mark_success(request)
            return redirect(next_url(request))
        mark_invalid(request, form)
    return render(request, 'accounts/two_factor.html', {
        'form': form,
        'is_setup': False,
        'next': next_url(request),
        'title': 'Двухфакторная защита',
    })
