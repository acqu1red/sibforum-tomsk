import json
from functools import wraps

from django.http import HttpResponse, JsonResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from forums.models import Forum
from forums.security import check_captcha, check_registration_rate_limit, client_ip
from .models import Registration, Ticket
from .selection import RegistrationError
from .tickets import build_ticket_pdf, ticket_qr_png
from .workflow import decide_item, registration_by_token, registration_payload, submit_registration, verify_email


def json_response(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={'ensure_ascii': False})


def parse_json(request):
    length = int(request.headers.get('Content-Length') or 0)
    if length <= 0 or length > 64 * 1024:
        raise RegistrationError('bad_request', 'Некорректный размер запроса.', status=400)
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        raise RegistrationError('bad_request', 'Некорректный JSON.', status=400)
    if not isinstance(payload, dict):
        raise RegistrationError('bad_request', 'Ожидался JSON-объект.', status=400)
    return payload


def registration_api(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except RegistrationError as error:
            return json_response({'ok': False, 'error': error.code, 'message': error.message}, status=error.status)
    return wrapped


def staff_api(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return json_response({'ok': False, 'error': 'authentication_required'}, status=401)
        if not request.user.is_staff:
            return json_response({'ok': False, 'error': 'permission_denied'}, status=403)
        permission = 'registrations.change_registrationitem' if view.__name__ == 'admin_decision' else 'registrations.view_registration'
        if not request.user.has_perm(permission):
            return json_response({'ok': False, 'error': 'permission_denied'}, status=403)
        return view(request, *args, **kwargs)
    return wrapped


def published_forum(payload):
    forum = Forum.objects.filter(slug=str(payload.get('forum') or ''), status=Forum.Status.PUBLISHED).first()
    if not forum:
        raise RegistrationError('forum_not_found', 'Форум не найден или регистрация закрыта.', status=404)
    return forum


@csrf_exempt
@require_POST
@registration_api
def submit(request):
    payload = parse_json(request)
    forum = published_forum(payload)
    ip_address = client_ip(request)
    check_registration_rate_limit(ip_address, 'submit')
    check_captcha(payload.get('captcha_token'), ip_address)
    result = submit_registration(
        forum,
        payload.get('person'),
        payload.get('selections'),
        payload.get('consents'),
        request_meta={'ip_address': ip_address, 'user_agent': request.META.get('HTTP_USER_AGENT', '')},
    )
    return json_response(result)


@csrf_exempt
@require_POST
@registration_api
def verify(request):
    payload = parse_json(request)
    forum = published_forum(payload)
    check_registration_rate_limit(client_ip(request), 'verify')
    registration, token = verify_email(forum, payload.get('email'), payload.get('code'))
    return json_response({'ok': True, 'token': token, 'registration': registration_payload(registration)})


@never_cache
@require_GET
@registration_api
def personal_registration(request):
    registration = registration_by_token(request.GET.get('t', ''))
    if not registration:
        raise RegistrationError('not_found', 'Личная ссылка недействительна.', status=404)
    return json_response({'ok': True, 'registration': registration_payload(registration)})


@never_cache
@require_GET
@staff_api
@registration_api
def admin_registrations(request):
    registrations = Registration.objects.select_related('participant__forum')
    forum_slug = request.GET.get('forum')
    if forum_slug:
        registrations = registrations.filter(participant__forum__slug=forum_slug)
    status = request.GET.get('status')
    if status:
        registrations = registrations.filter(items__status=status).distinct()
    return json_response({'items': [registration_payload(registration) for registration in registrations[:200]]})


@require_POST
@staff_api
@registration_api
def admin_decision(request, item_id):
    payload = parse_json(request)
    item = decide_item(
        item_id,
        str(payload.get('action') or ''),
        request.user,
        note=payload.get('note') or '',
        target_event_id=payload.get('target_event_id'),
        lot_ids=payload.get('lot_ids'),
    )
    return json_response({'ok': True, 'registration': registration_payload(item.registration)})


def authorized_ticket(request, public_id):
    ticket = Ticket.objects.filter(public_id=public_id, status=Ticket.Status.ACTIVE).select_related('registration__participant').first()
    if not ticket:
        raise RegistrationError('not_found', 'Билет не найден.', status=404)
    if request.user.is_authenticated and request.user.is_staff and (request.user.has_perm('registrations.view_ticket') or request.user.has_perm('registrations.add_checkin')):
        return ticket
    registration = registration_by_token(request.GET.get('t', ''))
    if not registration or registration.id != ticket.registration_id:
        raise RegistrationError('not_found', 'Билет не найден.', status=404)
    return ticket


@never_cache
@require_GET
@registration_api
def ticket_qr(request, public_id):
    ticket = authorized_ticket(request, public_id)
    response = HttpResponse(ticket_qr_png(ticket), content_type='image/png')
    response['Content-Disposition'] = f'inline; filename="ticket-{ticket.public_id}-qr.png"'
    response['Cache-Control'] = 'no-store'
    return response


@never_cache
@require_GET
@registration_api
def ticket_pdf(request, public_id):
    ticket = authorized_ticket(request, public_id)
    response = HttpResponse(build_ticket_pdf(ticket.registration), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="ticket-{ticket.public_id}.pdf"'
    response['Cache-Control'] = 'no-store'
    return response
