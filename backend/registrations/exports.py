"""Live staff reports. Downloads never change registrations or voting results."""
import uuid
from collections import Counter

from django.contrib import admin
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from forums.models import Event, Forum
from .models import EmailChallenge, Registration, RegistrationItem
from .reports import XLSX_MIME, csv_bytes, file_response, log_export, report_snapshot, timestamp, xlsx_bytes
from .selection import RegistrationError
from .views import registration_api, staff_api

PERSON_HEADERS = ['ID заявки', 'Фамилия', 'Имя', 'Отчество', 'ФИО', 'E-mail', 'Телефон', 'Организация', 'Должность', 'Категория', 'Город', 'Источник', 'Комментарий', 'Заявка создана', 'Почта подтверждена']
ITEM_HEADERS = PERSON_HEADERS + ['День', 'Дата', 'Начало', 'Окончание', 'Событие', 'Тип события', 'Статус', 'Лоты', 'Платно', 'Цена', 'Порядок оплаты', 'Комментарий решения', 'Кто решил', 'Когда решил', 'Версия заявки']
SUMMARY_HEADERS = PERSON_HEADERS + ['События', 'Лоты', 'Статусы', 'Версия заявки']
EVENT_HEADERS = ['ID события', 'Дата', 'Начало', 'Событие', 'Тип события', 'Всего записей', 'Подтверждено', 'На рассмотрении', 'Одобрено', 'Отклонено', 'Отменено участником', 'Отменено администратором', 'Почта не подтверждена']
UNVERIFIED = 'unverified'
STATUS_CHOICES = list(RegistrationItem.Status.choices) + [(UNVERIFIED, 'Почта не подтверждена (предварительный выбор)')]
STATUS_LABELS = dict(STATUS_CHOICES)


def person_row(registration):
    participant = registration.participant
    return [
        str(registration.id), participant.last_name, participant.first_name, participant.middle_name,
        participant.full_name, participant.email, '+' + participant.phone if participant.phone else '',
        participant.organization, participant.position, participant.category, participant.city,
        participant.source, participant.comment, timestamp(registration.created_at),
        timestamp(registration.email_verified_at) if registration.email_verified_at else 'Нет',
    ]


def records_for_registration(registration, events, lots):
    records = [dict(event=item.event, status=item.status, item=item,
                    lots=', '.join(f'{link.lot.number} — {link.lot.title}' for link in item.lot_links.all()))
               for item in registration.items.all()]
    # Until email verification there are no bookings. Preserve the latest intended
    # selection in the report, explicitly labelled; never count it as a booking.
    if not records and not registration.email_verified_at and registration.export_challenges:
        challenge = registration.export_challenges[0]
        seen = set()
        for selection in challenge.pending_selection:
            event_id = str(selection.get('event_id', ''))
            event = events.get(event_id)
            if event and event_id not in seen:
                seen.add(event_id)
                chosen_lots = [lots[str(pk)] for pk in selection.get('lot_ids', [])
                               if str(pk) in lots and lots[str(pk)].event_id == event.id]
                records.append(dict(event=event, status=UNVERIFIED, item=None,
                                    lots=', '.join(f'{lot.number} — {lot.title}' for lot in chosen_lots)))
    return records


def item_row(registration, record):
    if record is None:
        return person_row(registration) + ['', '', '', '', '', '', 'Нет записей на мероприятия', '', '', '', '', '', '', '', registration.version]
    event, item = record['event'], record['item']
    return person_row(registration) + [
        event.day.title, event.day.date.isoformat(), event.start_time.strftime('%H:%M'), event.end_time.strftime('%H:%M'),
        event.title, event.get_kind_display(), STATUS_LABELS[record['status']], record['lots'],
        'да' if event.is_paid else 'нет', event.price if event.price is not None else '', event.payment_note,
        item.decision_note if item else '', item.decided_by.get_username() if item and item.decided_by else '',
        timestamp(item.decided_at) if item and item.decided_at else '', registration.version,
    ]


def summary_row(registration, records):
    events = '\n'.join(f"{r['event'].day.date:%d.%m.%Y}, {r['event'].start_time:%H:%M} — {r['event'].title} [{STATUS_LABELS[r['status']]}]" for r in records)
    return person_row(registration) + [events or 'Нет записей на мероприятия',
        '\n'.join(r['lots'] for r in records if r['lots']),
        ', '.join(dict.fromkeys(STATUS_LABELS[r['status']] for r in records)), registration.version]


def filters_from_request(request):
    forum = Forum.objects.filter(slug=request.GET.get('forum') or 'promtour').first()
    if not forum:
        raise RegistrationError('forum_not_found', 'Форум не найден.', status=404)
    event_id = request.GET.get('event') or None
    if event_id:
        try:
            event_id = str(uuid.UUID(event_id))
        except (ValueError, TypeError, AttributeError):
            raise RegistrationError('invalid_event', 'Некорректный идентификатор события.')
        if not Event.objects.filter(pk=event_id, day__forum=forum).exists():
            raise RegistrationError('invalid_event', 'Мероприятие не принадлежит выбранному форуму.')
    status = request.GET.get('status') or None
    if status and status not in STATUS_LABELS:
        raise RegistrationError('invalid_status', 'Некорректный статус заявки.')
    mode = request.GET.get('mode') or 'items'
    if mode not in ('full', 'items', 'summary', 'routes'):
        raise RegistrationError('invalid_mode', 'Некорректное представление выгрузки.')
    kind = request.GET.get('kind') or None
    if kind and kind not in Event.Kind.values:
        raise RegistrationError('invalid_kind', 'Некорректный тип мероприятия.')
    if mode == 'routes':
        kind = Event.Kind.ROUTE
    return forum, event_id, status, mode, kind


def registration_sheets(forum, event_id=None, status=None, mode='full', kind=None):
    """Derive every sheet from the same loaded records, applying filters together."""
    events = {str(event.pk): event for event in Event.objects.filter(day__forum=forum).select_related('day').prefetch_related('lots')}
    lots = {str(lot.pk): lot for event in events.values() for lot in event.lots.all()}
    registrations = Registration.objects.filter(participant__forum=forum).select_related('participant').prefetch_related(
        'items__event__day', 'items__lot_links__lot', 'items__decided_by',
        Prefetch('email_challenges', queryset=EmailChallenge.objects.filter(verified_at__isnull=True).only(
            'id', 'registration_id', 'pending_selection', 'created_at').order_by('-created_at', '-id'), to_attr='export_challenges'),
    ).order_by('participant__last_name', 'participant__first_name', 'id')
    summaries, details, routes, counts = [], [], [], {}
    for registration in registrations:
        records = [record for record in records_for_registration(registration, events, lots)
                   if (not event_id or str(record['event'].pk) == event_id)
                   and (not status or record['status'] == status)
                   and (not kind or record['event'].kind == kind)]
        if not records and (event_id or status or kind):
            continue
        summaries.append(summary_row(registration, records))
        details.extend(item_row(registration, record) for record in (records or [None]))
        for record in records:
            event = record['event']
            if event.kind == Event.Kind.ROUTE:
                routes.append(item_row(registration, record))
            counts.setdefault(event.pk, (event, Counter()))[1][record['status']] += 1
    statistics = []
    for event, values in sorted(counts.values(), key=lambda pair: (pair[0].day.date, pair[0].start_time, str(pair[0].id))):
        statistics.append([str(event.id), event.day.date.isoformat(), event.start_time.strftime('%H:%M'),
            event.title, event.get_kind_display(), sum(values.values()),
            *[values[value] for value in RegistrationItem.Status.values], values[UNVERIFIED]])
    sheets = []
    if mode in ('full', 'summary'):
        sheets.append({'title': 'Участники', 'headers': SUMMARY_HEADERS, 'rows': summaries})
    if mode in ('full', 'items', 'routes'):
        sheets.append({'title': 'Маршруты' if mode == 'routes' else 'Записи на мероприятия', 'headers': ITEM_HEADERS, 'rows': details})
    if mode == 'full':
        sheets.append({'title': 'Маршруты', 'headers': ITEM_HEADERS, 'rows': routes})
    sheets.append({'title': 'Статистика мероприятий', 'headers': EVENT_HEADERS, 'rows': statistics})
    return sheets


@never_cache
@require_GET
@staff_api
@registration_api
def registration_export(request, format):
    if format not in ('csv', 'xlsx'):
        raise RegistrationError('invalid_format', 'Поддерживаются CSV и XLSX.', status=404)
    with report_snapshot():
        forum, event_id, status, mode, kind = filters_from_request(request)
        sheets = registration_sheets(forum, event_id, status, mode, kind)
    filters = {'forum': forum.slug, 'event': event_id, 'status': status, 'mode': mode, 'kind': kind, 'format': format}
    rows = sheets[0]['rows']
    filename = f'registrations-{forum.slug}-{mode}-{timezone.now():%Y%m%d-%H%M%S}.{format}'
    sheets.append({'title': 'О выгрузке', 'headers': ['Параметр', 'Значение'], 'rows': [
        ['Сформировано (время Томска)', timestamp()], ['Форум', forum.title],
        ['Фильтры', str(filters)], ['Администратор', request.user.get_username()], ['Строк на первом листе', len(rows)],
        ['Обновление', 'Данные из базы на момент скачивания. Для обновления скачайте файл ещё раз.'],
        ['Статусы', 'Включены отменённые и отклонённые записи, если не выбран отдельный статус.'],
        ['Предварительный выбор', 'Почта не подтверждена: это намерение участника, не бронирование места.'],
        ['Время', 'Даты и время мероприятий и выгрузки указаны по Томску (Asia/Tomsk).'],
    ]})
    content = xlsx_bytes(sheets) if format == 'xlsx' else csv_bytes(sheets[0]['headers'], rows)
    log_export(request.user, 'registrations', filters, filename, len(rows), request.META.get('REMOTE_ADDR'))
    return file_response(content, filename, XLSX_MIME if format == 'xlsx' else 'text/csv; charset=utf-8')


@never_cache
@require_GET
@staff_member_required
@registration_api
def export_page(request):
    can_register = request.user.has_perm('registrations.view_registration')
    can_vote = request.user.has_perm('voting.view_contest')
    if not (can_register or can_vote):
        raise PermissionDenied
    # Preserve existing download links to /admin/exports/?format=xlsx.
    if request.GET.get('format'):
        return registration_export(request, request.GET['format'])
    forum = Forum.objects.filter(slug=request.GET.get('forum') or 'promtour').first()
    if not forum:
        raise RegistrationError('forum_not_found', 'Форум не найден.', status=404)
    context = {**admin.site.each_context(request), 'title': 'Выгрузки Excel', 'forum': forum,
        'forums': Forum.objects.order_by('-starts_at'), 'can_register': can_register, 'can_vote': can_vote,
        'events': Event.objects.filter(day__forum=forum).select_related('day').order_by('day__date', 'start_time', 'position') if can_register else [],
        'statuses': STATUS_CHOICES, 'kinds': Event.Kind.choices,
    }
    if can_vote:
        from voting.models import Contest
        context['contest'] = Contest.objects.filter(forum=forum).prefetch_related('nominations').first()
    response = render(request, 'registrations/export.html', context)
    response['Cache-Control'] = 'no-store'
    return response
