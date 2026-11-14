import re
import uuid
from datetime import date

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import NotificationOutbox, RegistrationItem
from .tickets import ticket_email_attachments

STATUS_LABELS = {
    'confirmed': 'подтверждено',
    'pending_review': 'на рассмотрении',
    'approved': 'одобрено',
    'rejected': 'отклонено',
    'cancelled_by_user': 'отменено участником',
    'cancelled_by_admin': 'отменено администратором',
}


def header(value, limit=180):
    return re.sub(r'\s+', ' ', str(value or '')).strip()[:limit]


def registration_lines(payload):
    lines = []
    for item in payload.get('items', []):
        event = item['event']
        line = f"• {event['day_title']}, {event['start_time']}–{event['end_time']} — {event['title']}: {STATUS_LABELS.get(item['status'], item['status'])}"
        if event.get('is_paid'):
            line += f"\n  Стоимость: {event['price']} ₽. {event['payment_note']}"
        if item.get('lots'):
            line += '\n  Лоты: ' + ', '.join(str(lot['number']) for lot in item['lots'])
        lines.append(line)
    return lines


def message_content(notification):
    payload = notification.payload
    kind = notification.kind
    if kind == 'email_verification':
        subject = f"Код подтверждения — {payload.get('forum', 'Сибирский форум')}"
        body = (
            f"Ваш код подтверждения: {payload.get('code', '')}\n\n"
            "Код действует 20 минут. Если вы не отправляли заявку, просто проигнорируйте это письмо."
        )
    elif kind == 'registration_summary':
        participant = payload.get('participant', {})
        subject = 'Ваша регистрация на Сибирский форум'
        lines = [f"Здравствуйте, {participant.get('full_name', 'участник')}!", '', 'Ваша заявка и статусы событий:', '']
        lines.extend(registration_lines(payload))
        if payload.get('personal_url'):
            lines.extend(['', 'Личная страница и актуальный статус:', payload['personal_url']])
        body = '\n'.join(lines)
    elif kind == 'moderation_request':
        registration = notification.registration
        participant = registration.participant if registration else None
        item = registration.items.filter(id=payload.get('item_id')).select_related('event').first() if registration else None
        event_title = item.event.title if item else payload.get('event_id', '')
        subject = f'Новая заявка на модерацию — {event_title}'
        lines = ['Поступила новая заявка, требующая решения.', '']
        if participant:
            lines.extend([
                f"ФИО: {participant.full_name}",
                f"Организация: {participant.organization}",
                f"Должность: {participant.position}",
                f"Телефон: +{participant.phone}",
                f"E-mail: {participant.email}",
            ])
        if item:
            lots = list(item.lot_links.select_related('lot'))
            lines.append(f'Событие: {event_title}')
            if lots:
                lines.append('Лоты: ' + ', '.join(str(link.lot.number) for link in lots))
        lines.append(f"ID элемента заявки: {payload.get('item_id', '')}")
        body = '\n'.join(lines)
    elif kind == 'moderation_decision':
        status = payload.get('status')
        accepted = status in ('approved', 'confirmed')
        declined = status in ('rejected', 'cancelled_by_admin')
        cancelled = status == 'cancelled_by_admin'
        decision_title = 'Ваша заявка подтверждена' if accepted else 'Ваша запись отменена' if cancelled else 'Ваша заявка не подтверждена' if declined else 'Статус заявки изменился'
        subject = decision_title + ' — ' + payload.get('event', '')
        decision_text = 'Ваша заявка подтверждена.' if accepted else 'Ваша запись на мероприятие отменена.' if cancelled else 'К сожалению, заявка на это мероприятие не подтверждена.' if declined else 'Статус вашей заявки изменился.'
        lines = ['Здравствуйте!', '', decision_text, '', f"Событие: {payload.get('event', '')}"]
        if payload.get('day'):
            lines.append(f"Дата: {date.fromisoformat(payload['day']).strftime('%d.%m.%Y')}, начало: {payload.get('time', '')}")
        if payload.get('venue'):
            lines.append(f"Площадка: {payload['venue']}")
        note = payload.get('note', '')
        generic_note = note in ('', 'Отклонено администратором', 'Отменено администратором')
        if declined and payload.get('kind') == 'route' and generic_note:
            lines.extend(['', 'На выбранном маршруте нет свободных мест. Пожалуйста, выберите и забронируйте другой маршрут.'])
        elif declined:
            lines.extend(['', 'Вы можете выбрать другое мероприятие или маршрут.'])
        if payload.get('previous_event') and payload.get('previous_event') != payload.get('event'):
            lines.append(f"Прежний маршрут: {payload['previous_event']}")
        if payload.get('note'):
            lines.append(f"Комментарий: {payload['note']}")
        personal_url = payload.get('personal_url') or settings.PUBLIC_SITE_URL.rstrip('/') + '/#registration'
        lines.extend(['', 'Открыть вашу заявку и актуальные статусы:', personal_url])
        if declined:
            lines.extend(['', 'На странице заявки нажмите «Изменить мероприятия», выберите другой маршрут и подтвердите новый выбор кодом из письма.'])
        body = '\n'.join(lines)
    elif kind == 'voting_verification':
        subject = f"Код для голосования — {payload.get('contest', 'Индустриальный код')}"
        body = (
            f"Ваш код для подтверждения голосования: {payload.get('code', '')}\n\n"
            "Код действует 20 минут. Если вы не голосовали, просто проигнорируйте это письмо."
        )
    elif kind == 'voting_confirmation':
        subject = f"Ваш голос принят — {payload.get('contest', 'Индустриальный код')}"
        selected = payload.get('selected') or []
        body = 'Ваш бюллетень принят. Спасибо за участие в голосовании.'
        if selected:
            body += '\n\nВаш выбор:\n' + '\n'.join('• ' + str(name) for name in selected)
    else:
        raise ValueError(f'Неизвестный тип уведомления: {kind}')
    return header(subject), body


def claim_notification(now=None):
    now = now or timezone.now()
    stale = now - timezone.timedelta(minutes=10)
    with transaction.atomic():
        notification = NotificationOutbox.objects.select_for_update(skip_locked=True).filter(
            Q(status=NotificationOutbox.Status.PENDING, next_attempt_at__lte=now)
            | Q(status=NotificationOutbox.Status.SENDING, locked_at__lt=stale)
        ).order_by('created_at').first()
        if not notification:
            return None
        notification.status = NotificationOutbox.Status.SENDING
        notification.lock_token = uuid.uuid4()
        notification.locked_at = now
        notification.attempts += 1
        notification.save(update_fields=('status', 'lock_token', 'locked_at', 'attempts', 'updated_at'))
        return notification


def process_one(now=None):
    notification = claim_notification(now)
    if not notification:
        return None
    message_id = f'<{notification.id}@siberianforum.local>'
    try:
        subject, body = message_content(notification)
        message = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[notification.recipient],
            headers={'Message-ID': message_id},
        )
        if notification.registration and notification.kind in ('registration_summary', 'moderation_decision'):
            for filename, content, mimetype in ticket_email_attachments(notification.registration):
                message.attach(filename, content, mimetype)
            if message.attachments:
                body += '\n\nВо вложении — электронный билет с QR-кодом.'
                message.body = body
        message.send(fail_silently=False)
    except Exception as error:
        notification.status = NotificationOutbox.Status.PENDING if notification.attempts < 5 else NotificationOutbox.Status.FAILED
        notification.next_attempt_at = timezone.now() + timezone.timedelta(seconds=min(900, 30 * (2 ** notification.attempts)))
        notification.locked_at = None
        notification.lock_token = None
        notification.last_error = str(error)[:1000]
        notification.save()
        return notification.status

    payload = dict(notification.payload)
    payload.pop('code', None)
    payload.pop('personal_url', None)
    notification.payload = payload
    notification.status = NotificationOutbox.Status.SENT
    notification.sent_at = timezone.now()
    notification.provider_message_id = message_id
    notification.locked_at = None
    notification.lock_token = None
    notification.last_error = ''
    notification.save()
    return notification.status


def process_batch(limit=20):
    counts = {'sent': 0, 'pending': 0, 'failed': 0, 'empty': 0}
    for _ in range(limit):
        result = process_one()
        if result is None:
            counts['empty'] += 1
            break
        counts[result] += 1
    return counts
