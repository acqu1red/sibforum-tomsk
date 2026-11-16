"""Staff tools for a participant's existing registration and ticket."""
import secrets
import uuid

from django.contrib import admin, messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .models import NotificationOutbox, Registration, Ticket
from .selection import RegistrationError
from .tickets import build_ticket_pdf, ticket_qr_png
from .workflow import decision_personal_url, queue_notification, registration_payload


def can_view_registration(user):
    return user.has_perm('registrations.view_registration') or user.has_perm('registrations.change_registration')


def can_view_ticket(user):
    return can_view_registration(user) and (user.has_perm('registrations.view_ticket') or user.has_perm('registrations.change_ticket'))


def assistance_url(registration):
    return reverse('registration-assistance', args=[registration.pk])


class ParticipantAssistanceMixin:
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('participant', 'ticket') if self.model is Registration else qs.select_related('registration__ticket')

    def get_list_display(self, request):
        fields = super().get_list_display(request)
        may_send = request.user.has_perm('registrations.change_registration')
        may_download = can_view_ticket(request.user)
        if not may_send and not may_download:
            return fields

        @admin.display(description='Письмо и билет')
        def participant_tools(obj):
            registration = obj if isinstance(obj, Registration) else getattr(obj, 'registration', None)
            if not registration:
                return 'Нет заявки'
            send = format_html('<button type="button" class="participant-resend" data-registration-resend="{}">Отправить письмо ещё раз</button>',
                               reverse('registration-resend', args=[registration.pk])) if may_send else ''
            link = format_html('<a class="participant-ticket-link" href="{}">QR / билет</a>', assistance_url(registration)) if may_download else ''
            return format_html('<div class="participant-tools">{}{}<span data-resend-status role="status"></span></div>', send, link)
        return (fields[0], participant_tools, *fields[1:])

    def get_readonly_fields(self, request, obj=None):
        fields = super().get_readonly_fields(request, obj)
        return (*fields, 'assistance_link') if can_view_registration(request.user) else fields

    @admin.display(description='Письмо и билет')
    def assistance_link(self, obj):
        registration = obj if isinstance(obj, Registration) else getattr(obj, 'registration', None)
        if not registration:
            return 'Заявка ещё не создана'
        return format_html('<a class="button" href="{}">Открыть письмо и билет участника</a>', assistance_url(registration))


@transaction.atomic
def resend_email(registration_id, actor, request_key):
    if not actor.is_active or not actor.is_staff or not actor.has_perm('registrations.change_registration'):
        raise PermissionDenied
    try:
        request_key = str(uuid.UUID(str(request_key)))
    except (ValueError, TypeError, AttributeError):
        raise RegistrationError('invalid_request', 'Обновите страницу и повторите отправку.')
    registration = get_object_or_404(Registration.objects.select_for_update(of=('self',)).select_related('participant__forum'), pk=registration_id)
    key = f'manual-resend:{registration.pk}:{request_key}'
    existing = NotificationOutbox.objects.filter(dedup_key=key).first()
    if existing:
        return existing, False
    recent = registration.notifications.filter(dedup_key__startswith='manual-resend:',
        created_at__gt=timezone.now()-timezone.timedelta(seconds=60)).exclude(status__in=('failed', 'cancelled')).exists()
    if recent:
        raise RegistrationError('resend_too_soon', 'Письмо уже отправляется. Подождите одну минуту перед повторной отправкой.', status=429)
    if registration.email_verified:
        kind = 'registration_summary'
        payload = registration_payload(registration)
        payload['personal_url'] = decision_personal_url(registration)
    else:
        challenge = registration.email_challenges.select_for_update().filter(verified_at__isnull=True).first()
        if not challenge or not challenge.pending_selection:
            raise RegistrationError('missing_request', 'Нет незавершённой заявки для подтверждения. Попросите участника заполнить регистрацию на сайте.', status=409)
        if challenge.pending_person.get('email', registration.participant.email).lower() != registration.participant.email.lower():
            raise RegistrationError('email_mismatch', 'Адрес в заявке отличается от карточки участника. Попросите участника повторить регистрацию с актуальной почтой.', status=409)
        code = f'{secrets.randbelow(1000000):06d}'
        challenge.set_code(code)
        challenge.attempts = 0
        challenge.expires_at = timezone.now()+timezone.timedelta(minutes=20)
        challenge.save(update_fields=('code_hash', 'attempts', 'expires_at', 'updated_at'))
        registration.notifications.filter(kind='email_verification', status__in=('pending', 'failed')).update(status='cancelled')
        kind = 'email_verification'
        payload = {'code': code, 'forum': registration.participant.forum.title, 'challenge_id': str(challenge.pk)}
    notification = queue_notification(registration, kind, registration.participant.email, payload, key)
    LogEntry.objects.log_actions(user_id=actor.pk, queryset=[registration], action_flag=CHANGE,
        change_message='Повторное письмо участнику: '+notification.get_kind_display())
    return notification, True


@staff_member_required
@never_cache
@require_GET
def participant_help(request, registration_id):
    if not can_view_registration(request.user):
        raise PermissionDenied
    registration = get_object_or_404(Registration.objects.select_related('participant__forum', 'ticket'), pk=registration_id)
    ticket = getattr(registration, 'ticket', None)
    active_ticket = ticket if ticket and ticket.status == Ticket.Status.ACTIVE and registration.email_verified else None
    context = {**admin.site.each_context(request), 'title': 'Письмо и билет участника',
        'registration': registration, 'participant': registration.participant,
        'ticket': active_ticket if can_view_ticket(request.user) else None,
        'can_send': request.user.has_perm('registrations.change_registration'),
        'can_download': can_view_ticket(request.user), 'request_key': str(uuid.uuid4()),
        'items': registration.items.select_related('event__day'),
        'recent_mail': registration.notifications.filter(recipient=registration.participant.email).exclude(kind='moderation_request').order_by('-created_at')[:5],
        'back_url': reverse('admin:registrations_registration_changelist')}
    return render(request, 'registrations/assistance.html', context)


@staff_member_required
@never_cache
@require_POST
def resend(request, registration_id):
    if not request.user.has_perm('registrations.change_registration'):
        raise PermissionDenied
    wants_json = request.headers.get('Accept') == 'application/json'
    try:
        notification, created = resend_email(registration_id, request.user, request.POST.get('request_key'))
        label = 'Новый код подтверждения' if notification.kind == 'email_verification' else 'Письмо с актуальной заявкой'
        message = (f'{label}: отправка на {notification.recipient} поставлена в очередь.' if created
                   else 'Это письмо уже поставлено в очередь. Повторная копия не создана.')
    except RegistrationError as error:
        if wants_json:
            return JsonResponse({'ok': False, 'message': error.message}, status=error.status)
        messages.error(request, error.message)
    else:
        if wants_json:
            return JsonResponse({'ok': True, 'message': message, 'status': notification.status})
        messages.success(request, message)
    return redirect('registration-assistance', registration_id=registration_id)


def active_staff_ticket(request, registration_id):
    if not can_view_ticket(request.user):
        raise PermissionDenied
    return get_object_or_404(Ticket.objects.select_related('registration__participant__forum'),
        registration_id=registration_id, status=Ticket.Status.ACTIVE, registration__email_verified_at__isnull=False)


@staff_member_required
@never_cache
@require_GET
def download_qr(request, registration_id):
    ticket = active_staff_ticket(request, registration_id)
    response = HttpResponse(ticket_qr_png(ticket), content_type='image/png')
    disposition = 'attachment' if request.GET.get('download') == '1' else 'inline'
    response['Content-Disposition'] = f'{disposition}; filename="ticket-{ticket.public_id}-qr.png"'
    return response


@staff_member_required
@never_cache
@require_GET
def download_pdf(request, registration_id):
    ticket = active_staff_ticket(request, registration_id)
    response = HttpResponse(build_ticket_pdf(ticket.registration), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="ticket-{ticket.public_id}.pdf"'
    return response
