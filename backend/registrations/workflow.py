import hashlib
import secrets

from django.conf import settings
from django.core import signing
from django.core.exceptions import ValidationError
from django.contrib.auth.hashers import check_password
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare, salted_hmac

from forums.models import Event
from .models import (
    Consent,
    EmailChallenge,
    NotificationOutbox,
    Participant,
    Registration,
    RegistrationItem,
    RegistrationItemHistory,
    RegistrationItemLot,
)
from .selection import RegistrationError, add_history, apply_selection, normalize_person, normalize_selection
from .tickets import ensure_ticket, ticket_payload


def token_hash(token):
    return hashlib.sha256(token.encode('ascii')).hexdigest()


def decision_token_version(registration):
    return salted_hmac('moderation-access-version', registration.access_token_hash).hexdigest()[:20]


def decision_personal_url(registration):
    if not registration.email_verified or not registration.access_token_hash:
        return settings.PUBLIC_SITE_URL.rstrip('/') + '/#registration'
    token = signing.dumps({'r': str(registration.pk), 'v': decision_token_version(registration)},
                          salt='moderation-access', compress=True)
    return settings.PUBLIC_SITE_URL.rstrip('/') + '/promtour/?t=' + token + '#registration'


def queue_notification(registration, kind, recipient, payload, dedup_key):
    if not recipient:
        return None
    notification, _ = NotificationOutbox.objects.get_or_create(
        dedup_key=dedup_key,
        defaults={
            'registration': registration,
            'kind': kind,
            'recipient': recipient,
            'template_version': '1.0',
            'payload': payload,
        },
    )
    return notification


@transaction.atomic
def submit_registration(forum, person_payload, selection_payload, consents, request_meta=None):
    person = normalize_person(person_payload)
    normalize_selection(forum, selection_payload)
    if not isinstance(consents, dict) or consents.get('pd') is not True or consents.get('policy') is not True:
        raise RegistrationError('consents_required', 'Нужны согласие на обработку персональных данных и ознакомление с политикой.')

    participant, _ = Participant.objects.get_or_create(
        forum=forum,
        email=person['email'],
        defaults=person,
    )
    registration, _ = Registration.objects.get_or_create(participant=participant)
    registration.email_challenges.filter(verified_at__isnull=True).delete()
    NotificationOutbox.objects.filter(
        registration=registration,
        kind='email_verification',
        status=NotificationOutbox.Status.PENDING,
    ).update(status=NotificationOutbox.Status.CANCELLED)

    challenge = EmailChallenge(
        registration=registration,
        pending_person=person,
        pending_selection=selection_payload,
        expires_at=timezone.now() + timezone.timedelta(minutes=20),
    )
    code = f'{secrets.randbelow(1000000):06d}'
    challenge.set_code(code)
    challenge.save()
    queue_notification(
        registration,
        'email_verification',
        person['email'],
        {'code': code, 'forum': forum.title, 'challenge_id': str(challenge.id)},
        f'email-verification:{challenge.id}',
    )

    request_meta = request_meta or {}
    for document_type in ('pd', 'policy', 'media', 'news'):
        Consent.objects.create(
            registration=registration,
            document_type=document_type,
            version=str(consents.get(document_type + '_version') or '1.0'),
            accepted=consents.get(document_type) is True,
            ip_address=request_meta.get('ip_address'),
            user_agent=str(request_meta.get('user_agent') or '')[:300],
        )

    response = {
        'ok': True,
        'status': 'verification_required',
        'delivery': 'queued',
        'expires_at': challenge.expires_at.isoformat(),
    }
    if settings.DEBUG:
        response['debug_code'] = code
    return response


def registration_payload(registration):
    participant = registration.participant
    items = []
    for item in registration.items.select_related('event__day').prefetch_related('lot_links__lot'):
        items.append({
            'id': str(item.id),
            'status': item.status,
            'decision_note': item.decision_note,
            'event': {
                'id': str(item.event.id),
                'title': item.event.title,
                'day': item.event.day.date.isoformat(),
                'day_title': item.event.day.title,
                'start_time': item.event.start_time.strftime('%H:%M'),
                'end_time': item.event.end_time.strftime('%H:%M'),
                'is_paid': item.event.is_paid,
                'price': str(item.event.price) if item.event.is_paid else None,
                'payment_note': item.event.payment_note if item.event.is_paid else '',
            },
            'lots': [
                {
                    'id': str(link.lot.id),
                    'number': link.lot.number,
                    'title': link.lot.title,
                }
                for link in item.lot_links.all()
            ],
        })
    return {
        'id': str(registration.id),
        'email_verified': registration.email_verified,
        'version': registration.version,
        'participant': {
            'last_name': participant.last_name,
            'first_name': participant.first_name,
            'middle_name': participant.middle_name,
            'full_name': participant.full_name,
            'email': participant.email,
            'phone': participant.phone,
            'organization': participant.organization,
            'position': participant.position,
            'category': participant.category,
            'city': participant.city,
            'source': participant.source,
            'comment': participant.comment,
        },
        'items': items,
        'ticket': ticket_payload(getattr(registration, 'ticket', None)),
    }


def verify_email(forum, email, code):
    email = str(email or '').strip().lower()
    registration = Registration.objects.filter(participant__forum=forum, participant__email=email).first()
    challenge = None
    if registration:
        challenge = registration.email_challenges.filter(verified_at__isnull=True).order_by('-created_at').first()
    if not challenge or not challenge.check_code(str(code or '')):
        raise RegistrationError('invalid_code', 'Код недействителен или истёк. Запросите новый код.')
    return complete_email_verification(registration.id, challenge.id, code)


@transaction.atomic
def complete_email_verification(registration_id, challenge_id, code):
    registration = Registration.objects.select_for_update().select_related('participant').get(id=registration_id)
    challenge = registration.email_challenges.select_for_update().get(id=challenge_id)
    if challenge.verified_at is not None or challenge.attempts > 5 or challenge.expires_at <= timezone.now() or not check_password(str(code or ''), challenge.code_hash):
        raise RegistrationError('invalid_code', 'Код недействителен или истёк. Запросите новый код.')

    now = timezone.now()
    for field, value in challenge.pending_person.items():
        setattr(registration.participant, field, value)
    registration.participant.save()
    challenge.verified_at = now
    challenge.save(update_fields=('verified_at', 'updated_at'))
    registration.email_verified_at = registration.email_verified_at or now
    raw_token = secrets.token_urlsafe(32)
    registration.access_token_hash = token_hash(raw_token)
    registration.token_issued_at = now
    registration.save(update_fields=('email_verified_at', 'access_token_hash', 'token_issued_at', 'updated_at'))

    apply_selection(registration, challenge.pending_selection)
    registration.refresh_from_db()
    ensure_ticket(registration)
    payload = registration_payload(registration)
    payload['personal_url'] = settings.PUBLIC_SITE_URL + '/promtour/?t=' + raw_token
    queue_notification(
        registration,
        'registration_summary',
        registration.participant.email,
        payload,
        f'registration-summary:{registration.id}:v{registration.version}',
    )
    for item in registration.items.filter(status=RegistrationItem.Status.PENDING_REVIEW).select_related('event'):
        queue_notification(
            registration,
            'moderation_request',
            item.event.curator_email,
            {'registration_id': str(registration.id), 'event_id': str(item.event.id), 'item_id': str(item.id)},
            f'moderation-request:{item.id}:v{registration.version}',
        )
    return registration, raw_token


def registration_by_token(token):
    if not token or not token.isascii() or len(token) > 200:
        return None
    registration = Registration.objects.select_related('participant__forum').filter(
        access_token_hash=token_hash(token),
        email_verified_at__isnull=False,
    ).first()
    if registration:
        return registration
    try:
        payload = signing.loads(token, salt='moderation-access', max_age=timezone.timedelta(days=30))
        if not isinstance(payload, dict):
            return None
        registration = Registration.objects.select_related('participant__forum').filter(
            pk=payload.get('r'), email_verified_at__isnull=False).first()
        if registration and registration.access_token_hash and constant_time_compare(
                str(payload.get('v', '')), decision_token_version(registration)):
            return registration
    except (signing.BadSignature, ValueError, TypeError, ValidationError):
        pass
    return None


@transaction.atomic
def decide_item(item_id, action, admin_user, note='', target_event_id=None, lot_ids=None):
    item = RegistrationItem.objects.select_for_update().filter(id=item_id).first()
    if not item:
        raise RegistrationError('item_not_found', 'Элемент заявки не найден.', status=404)
    previous_status = item.status
    previous_event = item.event
    now = timezone.now()
    target_event = None

    if action in ('approve', 'reject'):
        if previous_event.registration_policy != Event.RegistrationPolicy.MODERATED or previous_status != RegistrationItem.Status.PENDING_REVIEW:
            raise RegistrationError('invalid_transition', 'Решение доступно только для заявки на модерации.', status=409)
        item.status = RegistrationItem.Status.APPROVED if action == 'approve' else RegistrationItem.Status.REJECTED
    elif action == 'cancel':
        if previous_status not in RegistrationItem.ACTIVE_STATUSES:
            raise RegistrationError('invalid_transition', 'Заявка уже неактивна.', status=409)
        item.status = RegistrationItem.Status.CANCELLED_BY_ADMIN
    elif action == 'move':
        if previous_status not in (RegistrationItem.Status.PENDING_REVIEW, RegistrationItem.Status.APPROVED):
            raise RegistrationError('invalid_transition', 'Перевести можно только активную модерируемую заявку.', status=409)
        target_event = Event.objects.filter(
            id=target_event_id,
            day__forum=previous_event.day.forum,
            kind=previous_event.kind,
            registration_policy=Event.RegistrationPolicy.MODERATED,
            is_published=True,
        ).first()
        if not target_event:
            raise RegistrationError('invalid_target', 'Новое событие недоступно для перевода.')
        if target_event.id == previous_event.id:
            raise RegistrationError('invalid_target', 'Выберите другой маршрут.')
        if item.registration.items.filter(event=target_event).exists():
            raise RegistrationError('target_already_selected', 'Этот маршрут уже есть в заявке.', status=409)
        selections = [
            {'event_id': str(other.event_id), 'lot_ids': [str(link.lot_id) for link in other.lot_links.all()]}
            for other in item.registration.items.exclude(id=item.id).filter(status__in=RegistrationItem.ACTIVE_STATUSES)
        ]
        selections.append({'event_id': str(target_event.id), 'lot_ids': lot_ids or []})
        normalize_selection(item.registration.participant.forum, selections)
        item.event = target_event
        item.status = RegistrationItem.Status.APPROVED
        item.lot_links.all().delete()
        if lot_ids:
            for lot in target_event.lots.filter(is_published=True, id__in=lot_ids):
                RegistrationItemLot.objects.create(item=item, lot=lot)
    else:
        raise RegistrationError('unknown_action', 'Неизвестное действие.')

    item.decision_note = str(note or '').strip()[:2000]
    item.decided_at = now
    item.decided_by = admin_user
    item.save()
    action_name = 'moved' if action == 'move' else action
    add_history(
        item,
        action_name,
        item.status,
        RegistrationItemHistory.ActorKind.ADMIN,
        from_status=previous_status,
        note=item.decision_note,
        actor_user=admin_user,
        from_event=previous_event if action == 'move' else None,
        to_event=target_event if action == 'move' else None,
    )
    registration = item.registration
    registration.version += 1
    registration.save(update_fields=('version', 'updated_at'))
    ensure_ticket(registration)
    history = item.history.latest('created_at')
    queue_notification(
        registration,
        'moderation_decision',
        registration.participant.email,
        {
            'action': action_name,
            'previous_event': previous_event.title,
            'event': item.event.title,
            'note': item.decision_note,
            'status': item.status,
            'kind': item.event.kind,
            'day': item.event.day.date.isoformat(),
            'time': item.event.start_time.strftime('%H:%M'),
            'venue': item.event.venue.name if item.event.venue else '',
            'personal_url': decision_personal_url(registration),
        },
        f'moderation-decision:{history.id}',
    )
    return item
