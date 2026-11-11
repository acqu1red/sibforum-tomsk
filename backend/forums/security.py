import ipaddress
import json
import urllib.parse
import urllib.request

from django.conf import settings
from django.utils import timezone

from registrations.models import RegistrationAttemptLog
from registrations.selection import RegistrationError


def client_ip(request):
    if settings.TRUST_PROXY_IP_HEADER:
        value = request.META.get('HTTP_X_REAL_IP', '')
        try:
            return str(ipaddress.ip_address(value))
        except ValueError:
            pass
    return request.META.get('REMOTE_ADDR')


def check_captcha(token, ip_address):
    if not settings.YANDEX_SMARTCAPTCHA_SECRET:
        return
    if not token:
        raise RegistrationError('captcha_required', 'Подтвердите, что вы не робот.')
    payload = urllib.parse.urlencode({
        'secret': settings.YANDEX_SMARTCAPTCHA_SECRET,
        'token': token,
        'ip': ip_address or '',
    }).encode()
    request = urllib.request.Request(settings.YANDEX_SMARTCAPTCHA_URL, data=payload)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            result = json.load(response)
    except Exception:
        raise RegistrationError('captcha_unavailable', 'Не удалось проверить защиту от роботов. Повторите позже.', status=503)
    if result.get('status') != 'ok' and result.get('success') is not True:
        raise RegistrationError('captcha_invalid', 'Проверка защиты от роботов не пройдена.')


def check_registration_rate_limit(ip_address, action):
    if not ip_address:
        return
    threshold = timezone.now() - timezone.timedelta(minutes=10)
    if RegistrationAttemptLog.objects.filter(ip_address=ip_address, action=action, created_at__gte=threshold).count() >= 20:
        raise RegistrationError('rate_limited', 'Слишком много попыток. Повторите через 10 минут.', status=429)
    RegistrationAttemptLog.objects.create(ip_address=ip_address, action=action)
