from urllib.parse import urlencode
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.http import JsonResponse, Http404
from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from django.core.exceptions import ValidationError
from forums.models import Forum, Event
from .models import CheckIn
from .reports import report_snapshot, timestamp, xlsx_bytes, csv_bytes, file_response, XLSX_MIME, log_export


def scope(request):
    params = request.POST if request.method == 'POST' else request.GET
    forum_slug = params.get('forum', 'promtour')
    forum = Forum.objects.filter(slug=forum_slug).first()
    if not forum:
        raise Http404('Форум не найден')
    events = Event.objects.filter(day__forum=forum).select_related('day').order_by('day__date', 'start_time', 'position')
    event = None
    try:
        if params.get('event'):
            event = events.filter(id=params['event']).first()
            if not event:
                raise Http404('Мероприятие не найдено')
    except (ValueError, ValidationError):
        raise Http404('Некорректное мероприятие')
    values = {'forum': forum.slug}
    if event:
        values['event'] = str(event.id)
    return {'forum': forum, 'events': events, 'selected_event': event, 'scope_query': urlencode(values)}


@staff_member_required
@permission_required('registrations.export_checkin', raise_exception=True)
@never_cache
@require_GET
def attendance(request):
    context = scope(request)
    event, forum = context['selected_event'], context['forum']
    with report_snapshot():
        queryset = CheckIn.objects.filter(ticket__registration__participant__forum=forum).select_related(
            'ticket__registration__participant', 'event__day', 'admin_user').order_by('-created_at', '-id')
        if event:
            queryset = queryset.filter(event=event)
        records = list(queryset)
        rows = [[str(c.id), c.ticket.registration.participant.full_name,
                 c.ticket.registration.participant.organization,
                 c.event.title if c.event_id else 'Общий вход на форум',
                 timestamp(c.created_at), c.admin_user.get_username(), str(c.ticket.public_id)] for c in records]
        summary = {'marks': len(records), 'people': len({c.ticket_id for c in records}),
                   'general': sum(c.event_id is None for c in records), 'events': sum(c.event_id is not None for c in records)}
        headers = ['ID отметки', 'ФИО', 'Организация', 'Допуск', 'Время прибытия (Томск)', 'Пропустил', 'Номер билета']
        generated = timestamp()
    format = request.GET.get('format')
    if format in ('xlsx', 'csv'):
        sheets = [{'title': 'Пришедшие участники', 'headers': headers, 'rows': rows},
                  {'title': 'Статистика', 'headers': ['Показатель', 'Значение'], 'rows': [
                      ['Сформировано (Томск)', generated], ['Форум', forum.title],
                      ['Мероприятие', event.title if event else 'Все отметки'],
                      ['Людей с отметкой', summary['people']], ['Всего отметок', summary['marks']],
                      ['Общий вход', summary['general']], ['Допуски на мероприятия', summary['events']],
                      ['Правило', 'Сканирование без кнопки пропуска не считается приходом. Общий вход не означает посещение каждого мероприятия.'],
                      ['Обновление', 'Актуальная база на момент скачивания; для нового отчёта скачайте файл снова.']]}]
        filename = f'attendance-{forum.slug}-{generated.replace(".", "").replace(":", "").replace(" ", "-")}.{format}'
        data = xlsx_bytes(sheets) if format == 'xlsx' else csv_bytes(headers, rows)
        log_export(request.user, 'attendance', {'forum': forum.slug, 'event': str(event.id) if event else ''}, filename, len(rows), request.META.get('REMOTE_ADDR'))
        return file_response(data, filename, XLSX_MIME if format == 'xlsx' else 'text/csv; charset=utf-8')
    if format == 'json':
        return JsonResponse({'summary': summary, 'rows': rows[:100], 'generated': generated})
    return render(request, 'registrations/attendance.html', {**context, 'summary': summary, 'rows': rows[:100], 'generated': generated})
