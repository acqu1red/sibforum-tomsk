import re
import uuid

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from forums.models import ChoiceGroup, Event
from .models import RegistrationItem, RegistrationItemHistory, RegistrationItemLot


class RegistrationError(Exception):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def clean_text(value, limit):
    return re.sub(r'\s+', ' ', str(value or '')).strip()[:limit]


def normalize_person(payload):
    if not isinstance(payload, dict):
        raise RegistrationError('invalid_person', 'Некорректные данные участника.')
    person = {
        'last_name': clean_text(payload.get('last_name'), 100),
        'first_name': clean_text(payload.get('first_name'), 100),
        'middle_name': clean_text(payload.get('middle_name'), 100),
        'email': clean_text(payload.get('email'), 254).lower(),
        'phone': re.sub(r'\D', '', str(payload.get('phone') or '')),
        'organization': clean_text(payload.get('organization'), 200),
        'position': clean_text(payload.get('position'), 200),
        'category': clean_text(payload.get('category'), 60),
        'city': clean_text(payload.get('city'), 100),
        'source': clean_text(payload.get('source'), 100),
        'comment': clean_text(payload.get('comment'), 1000),
    }
    required = ('last_name', 'first_name', 'middle_name', 'email', 'phone', 'organization', 'position', 'category')
    missing = [field for field in required if not person[field]]
    if missing:
        raise RegistrationError('required_fields', 'Заполните обязательные поля: ' + ', '.join(missing) + '.')
    try:
        validate_email(person['email'])
    except DjangoValidationError:
        raise RegistrationError('invalid_email', 'Проверьте адрес электронной почты.')
    if person['phone'].startswith('8') and len(person['phone']) == 11:
        person['phone'] = '7' + person['phone'][1:]
    if len(person['phone']) != 11 or not person['phone'].startswith('7'):
        raise RegistrationError('invalid_phone', 'Нужен номер из 11 цифр, например +7 (999) 123-45-67.')
    return person


def normalize_selection(forum, selections):
    if not isinstance(selections, list) or not selections or len(selections) > 60:
        raise RegistrationError('invalid_selection', 'Выберите хотя бы одно событие.')
    event_ids = []
    raw_lots = {}
    for selection in selections:
        if not isinstance(selection, dict):
            raise RegistrationError('invalid_selection', 'Некорректный выбор событий.')
        try:
            event_id = str(uuid.UUID(str(selection.get('event_id') or '')))
        except (ValueError, TypeError, AttributeError):
            raise RegistrationError('unknown_event', 'Некорректный идентификатор события.')
        if event_id in event_ids:
            raise RegistrationError('duplicate_event', 'Одно событие выбрано несколько раз.')
        event_ids.append(event_id)
        lot_ids = selection.get('lot_ids') or []
        if not isinstance(lot_ids, list) or len(lot_ids) != len(set(map(str, lot_ids))):
            raise RegistrationError('duplicate_lot', 'Проверьте выбранные лоты.')
        try:
            raw_lots[event_id] = [str(uuid.UUID(str(lot_id))) for lot_id in lot_ids]
        except (ValueError, TypeError, AttributeError):
            raise RegistrationError('unknown_lot', 'Некорректный идентификатор лота.')

    events = list(Event.objects.filter(day__forum=forum, is_published=True, id__in=event_ids).select_related('day'))
    if len(events) != len(event_ids):
        raise RegistrationError('unknown_event', 'Одно из событий недоступно для регистрации.', status=404)
    events.sort(key=lambda event: event_ids.index(str(event.id)))
    allowed = {Event.RegistrationPolicy.AUTO, Event.RegistrationPolicy.MODERATED}
    if any(event.registration_policy not in allowed for event in events):
        raise RegistrationError('registration_not_allowed', 'На одно из событий нельзя записаться через эту форму.')

    for group in ChoiceGroup.objects.filter(day__forum=forum).prefetch_related('event_links'):
        group_event_ids = {str(link.event_id) for link in group.event_links.all()}
        count = sum(1 for event in events if str(event.id) in group_event_ids)
        if count < group.min_selections or count > group.max_selections:
            raise RegistrationError('choice_group_limit', f'В группе «{group.title}» допустимо от {group.min_selections} до {group.max_selections} событий.')

    for index, first in enumerate(events):
        for second in events[index + 1:]:
            if first.day_id != second.day_id:
                continue
            if first.start_time < second.end_time and second.start_time < first.end_time:
                raise RegistrationError('event_conflict', f'События «{first.title}» и «{second.title}» пересекаются по времени.')

    from .models import Lot
    normalized = []
    for event in events:
        lot_ids = raw_lots[str(event.id)]
        lots = list(Lot.objects.filter(event=event, is_published=True, id__in=lot_ids))
        if len(lots) != len(lot_ids):
            raise RegistrationError('unknown_lot', 'Один из лотов недоступен.', status=404)
        if event.kind != Event.Kind.EXCHANGE and lots:
            raise RegistrationError('lots_not_allowed', 'Лоты можно выбирать только для биржи.')
        if event.kind == Event.Kind.EXCHANGE:
            count = len(lots)
            if count < event.min_lot_selections:
                raise RegistrationError('lot_min_limit', 'Выберите хотя бы один лот биржи.')
            if event.max_lot_selections is not None and count > event.max_lot_selections:
                raise RegistrationError('lot_max_limit', f'Можно выбрать не более {event.max_lot_selections} лотов.')
        lots.sort(key=lambda lot: lot_ids.index(str(lot.id)))
        normalized.append({'event': event, 'lots': lots})
    return normalized


def initial_status(event):
    if event.registration_policy == Event.RegistrationPolicy.AUTO:
        return RegistrationItem.Status.CONFIRMED
    return RegistrationItem.Status.PENDING_REVIEW


def add_history(item, action, to_status, actor_kind, from_status='', note='', actor_user=None, from_event=None, to_event=None):
    RegistrationItemHistory.objects.create(
        item=item,
        action=action,
        from_event=from_event,
        to_event=to_event,
        from_status=from_status,
        to_status=to_status,
        note=note,
        actor_kind=actor_kind,
        actor_user=actor_user,
    )


@transaction.atomic
def apply_selection(registration, selections, actor_kind=RegistrationItemHistory.ActorKind.PARTICIPANT):
    normalized = normalize_selection(registration.participant.forum, selections)
    existing = {
        str(item.event_id): item
        for item in registration.items.select_for_update().select_related('event').prefetch_related('lot_links')
    }
    selected_ids = {str(selection['event'].id) for selection in normalized}
    now = timezone.now()
    changed = False

    for event_id, item in existing.items():
        if event_id not in selected_ids and item.status in RegistrationItem.ACTIVE_STATUSES:
            previous = item.status
            item.status = RegistrationItem.Status.CANCELLED_BY_USER
            item.decided_at = now
            item.decided_by = None
            item.decision_note = ''
            item.save(update_fields=('status', 'decided_at', 'decided_by', 'decision_note', 'updated_at'))
            add_history(item, 'cancelled', item.status, actor_kind, from_status=previous)
            changed = True

    for selection in normalized:
        event, lots = selection['event'], selection['lots']
        event_id = str(event.id)
        wanted_lot_ids = {str(lot.id) for lot in lots}
        item = existing.get(event_id)
        if item is None:
            item = RegistrationItem.objects.create(
                registration=registration,
                event=event,
                status=initial_status(event),
                decided_at=now if event.registration_policy == Event.RegistrationPolicy.AUTO else None,
            )
            for lot in lots:
                RegistrationItemLot.objects.create(item=item, lot=lot)
            add_history(item, 'created', item.status, actor_kind)
            changed = True
            continue

        previous = item.status
        previous_lot_ids = {str(link.lot_id) for link in item.lot_links.all()}
        lots_changed = previous_lot_ids != wanted_lot_ids
        next_status = initial_status(event)
        if event.registration_policy == Event.RegistrationPolicy.MODERATED and previous == RegistrationItem.Status.APPROVED and not lots_changed:
            next_status = previous
        elif event.registration_policy == Event.RegistrationPolicy.MODERATED and previous == RegistrationItem.Status.PENDING_REVIEW and not lots_changed:
            next_status = previous
        status_changed = previous != next_status
        if status_changed:
            item.status = next_status
            item.decided_at = now if next_status == RegistrationItem.Status.CONFIRMED else None
            item.decided_by = None
            item.decision_note = ''
            item.save(update_fields=('status', 'decided_at', 'decided_by', 'decision_note', 'updated_at'))
        if lots_changed:
            item.lot_links.all().delete()
            for lot in lots:
                RegistrationItemLot.objects.create(item=item, lot=lot)
        if status_changed or lots_changed:
            add_history(item, 'updated', next_status, actor_kind, from_status=previous, note='Изменён выбор событий или лотов.')
            changed = True

    if changed:
        registration.version += 1
        registration.save(update_fields=('version', 'updated_at'))
    return registration
