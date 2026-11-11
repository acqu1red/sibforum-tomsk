import uuid

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.http import require_GET

from forums.models import Event, Forum
from .models import Registration, RegistrationItem
from .reports import XLSX_MIME, csv_bytes, file_response, log_export, timestamp, xlsx_bytes
from .selection import RegistrationError
from .views import registration_api, staff_api

PERSON_HEADERS = ['ID заявки', 'Фамилия', 'Имя', 'Отчество', 'ФИО', 'E-mail', 'Телефон', 'Организация', 'Должность', 'Категория', 'Город', 'Источник', 'Комментарий']
ITEM_HEADERS = PERSON_HEADERS + ['День', 'Дата', 'Начало', 'Окончание', 'Событие', 'Тип события', 'Статус', 'Лоты', 'Платно', 'Цена', 'Порядок оплаты', 'Комментарий решения', 'Кто решил', 'Когда решил', 'Версия заявки']
SUMMARY_HEADERS = PERSON_HEADERS + ['События', 'Лоты', 'Статусы', 'Версия заявки']
EVENT_HEADERS = ['Событие', 'Всего', 'Подтверждено', 'На рассмотрении', 'Одобрено', 'Отклонено', 'Отменено участником', 'Отменено администратором']


def person_row(registration):
    participant = registration.participant
    return [
        str(registration.id), participant.last_name, participant.first_name, participant.middle_name,
        participant.full_name, participant.email, '+' + participant.phone, participant.organization,
        participant.position, participant.category, participant.city, participant.source, participant.comment,
    ]


def item_row(item):
    event = item.event
    lots = ', '.join(f'{link.lot.number} — {link.lot.title}' for link in item.lot_links.all())
    return person_row(item.registration) + [
        event.day.title, event.day.date.isoformat(), event.start_time.strftime('%H:%M'), event.end_time.strftime('%H:%M'),
        event.title, event.kind, item.status, lots, 'да' if event.is_paid else 'нет',
        str(event.price) if event.price is not None else '', event.payment_note,
        item.decision_note, item.decided_by.get_username() if item.decided_by else '',
        timestamp(item.decided_at) if item.decided_at else '', item.registration.version,
    ]


def summary_row(registration):
    items = list(registration.items.all())
    events = '\n'.join(
        f"{item.event.day.title}, {item.event.start_time:%H:%M} — {item.event.title} [{item.status}]"
        for item in items
    )
    lots = ', '.join(f'{link.lot.number} — {link.lot.title}' for item in items for link in item.lot_links.all())
    statuses = ', '.join(item.status for item in items)
    return person_row(registration) + [events, lots, statuses, registration.version]


def registrations_for_export(forum, event_id=None, status=None):
    registrations = Registration.objects.filter(participant__forum__slug=forum.slug)
    if event_id:
        registrations = registrations.filter(items__event_id=event_id)
    if status:
        registrations = registrations.filter(items__status=status)
    return registrations.select_related('participant__forum').prefetch_related(
        'items__event__day', 'items__lot_links__lot', 'items__decided_by',
    ).distinct()


def export_rows(registrations, mode, event_id=None, status=None):
    rows = []
    for registration in registrations:
        items = list(registration.items.all())
        if event_id:
            items = [item for item in items if str(item.event_id) == event_id]
        if status:
            items = [item for item in items if item.status == status]
        if mode == 'summary':
            rows.append(summary_row(registration))
        else:
            rows.extend(item_row(item) for item in items)
    return rows


def event_rows(registrations, event_id=None, status=None):
    counts = {}
    for registration in registrations:
        for item in registration.items.all():
            if event_id and str(item.event_id) != event_id:
                continue
            if status and item.status != status:
                continue
            title = item.event.title
            if title not in counts:
                counts[title] = {key: 0 for key in RegistrationItem.Status.values}
                counts[title]['total'] = 0
            counts[title]['total'] += 1
            counts[title][item.status] += 1
    return [
        [title, values['total'], values['confirmed'], values['pending_review'], values['approved'], values['rejected'], values['cancelled_by_user'], values['cancelled_by_admin']]
        for title, values in counts.items()
    ]


def filters_from_request(request):
    forum = Forum.objects.filter(slug=request.GET.get('forum') or 'promtour', status=Forum.Status.PUBLISHED).first()
    if not forum:
        raise RegistrationError('forum_not_found', 'Форум не найден.', status=404)
    event_id = request.GET.get('event') or None
    if event_id:
        try:
            event_id = str(uuid.UUID(event_id))
        except (ValueError, TypeError, AttributeError):
            raise RegistrationError('invalid_event', 'Некорректный идентификатор события.')
    status = request.GET.get('status') or None
    if status and status not in RegistrationItem.Status.values:
        raise RegistrationError('invalid_status', 'Некорректный статус заявки.')
    mode = request.GET.get('mode') or 'items'
    if mode not in ('items', 'summary'):
        raise RegistrationError('invalid_mode', 'Некорректное представление выгрузки.')
    return forum, event_id, status, mode


@require_GET
@staff_api
@registration_api
def registration_export(request, format):
    if format not in ('csv', 'xlsx'):
        raise RegistrationError('invalid_format', 'Поддерживаются CSV и XLSX.', status=404)
    forum, event_id, status, mode = filters_from_request(request)
    registrations = list(registrations_for_export(forum, event_id, status))
    rows = export_rows(registrations, mode, event_id, status)
    filename = f'registrations-{forum.slug}-{mode}-{timezone.now():%Y%m%d-%H%M}.{format}'
    filters = {'forum': forum.slug, 'event': event_id, 'status': status, 'mode': mode, 'format': format}
    if format == 'csv':
        headers = SUMMARY_HEADERS if mode == 'summary' else ITEM_HEADERS
        content = csv_bytes(headers, rows)
        content_type = 'text/csv; charset=utf-8'
    else:
        sheets = [{
            'title': 'По участникам' if mode == 'summary' else 'По событиям',
            'headers': SUMMARY_HEADERS if mode == 'summary' else ITEM_HEADERS,
            'rows': rows,
        }, {
            'title': 'Статистика событий',
            'headers': EVENT_HEADERS,
            'rows': event_rows(registrations, event_id, status),
        }, {
            'title': 'Метаданные',
            'headers': ['Параметр', 'Значение'],
            'rows': [
                ['Сформировано', timestamp()],
                ['Форум', forum.title],
                ['Представление', mode],
                ['Фильтры', str(filters)],
                ['Администратор', request.user.get_username()],
                ['Строк', len(rows)],
            ],
        }]
        content = xlsx_bytes(sheets)
        content_type = XLSX_MIME
    log_export(request.user, 'registrations', filters, filename, len(rows), request.META.get('REMOTE_ADDR'))
    return file_response(content, filename, content_type)


@staff_member_required
@permission_required('registrations.view_registration', raise_exception=True)
def export_page(request):
    forum, event_id, status, mode = filters_from_request(request)
    if request.GET.get('format'):
        return registration_export(request, request.GET['format'])
    events = Event.objects.filter(day__forum=forum).order_by('day__position', 'start_time', 'position')
    return render(request, 'registrations/export.html', {
        'forum': forum,
        'events': events,
        'statuses': RegistrationItem.Status.choices,
        'filters': {'event': event_id, 'status': status, 'mode': mode},
        'title': 'Выгрузки участников',
    })
