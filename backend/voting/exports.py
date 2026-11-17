"""Ballot-level exports, without anti-abuse identifiers or verification secrets."""
import uuid
from collections import Counter

from django.db.models import Prefetch
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET

from registrations.reports import XLSX_MIME, csv_bytes, file_response, log_export, report_snapshot, timestamp, xlsx_bytes
from .models import Ballot, Contest, Nominee, VoteSelection
from .views import staff_api, voting_api
from .workflow import VotingError

BALLOT_HEADERS = ['ID бюллетеня', 'Дата голосования (Томск)', 'Дата создания (Томск)', 'Статус', 'E-mail (если указан)', 'Способ', 'Выбранные номинации и проекты', 'Число выбранных проектов']
CHOICE_HEADERS = ['ID бюллетеня', 'Дата голосования (Томск)', 'Статус', 'E-mail (если указан)', 'Номинация', 'Проект / компания', 'ID номинации', 'ID проекта']
RESULT_HEADERS = ['Номинация', 'Проект / компания', 'Принято голосов', 'Бюллетеней с выбором в номинации', 'Принято бюллетеней в выгрузке']


def voting_sheets(contest, mode='full', status='submitted', nomination_id=None):
    selections = VoteSelection.objects.select_related('nomination', 'nominee').order_by('nomination__position', 'nominee__position', 'id')
    ballots = Ballot.objects.filter(contest=contest)
    if status != 'all':
        ballots = ballots.filter(status=status)
    if nomination_id:
        ballots = ballots.filter(selections__nomination_id=nomination_id).distinct()
    # Deliberately do not fetch browser/network/identity hashes or pending codes.
    ballots = ballots.only('id', 'status', 'email', 'created_at', 'submitted_at').order_by('submitted_at', 'created_at', 'id').prefetch_related(
        Prefetch('selections', queryset=selections, to_attr='export_selections'))
    ballot_rows, choice_rows, accepted, voters, submitted = [], [], Counter(), {}, 0
    for ballot in ballots:
        chosen = [choice for choice in ballot.export_selections if not nomination_id or str(choice.nomination_id) == nomination_id]
        if ballot.status == Ballot.Status.SUBMITTED:
            submitted += 1
            for choice in chosen:
                accepted[choice.nominee_id] += 1
                voters.setdefault(choice.nomination_id, set()).add(ballot.id)
        date = timestamp(ballot.submitted_at) if ballot.submitted_at else ''
        ballot_rows.append([str(ballot.id), date, timestamp(ballot.created_at), ballot.get_status_display(), ballot.email,
            'С почтой' if ballot.email else 'Анонимно, без почты',
            '\n'.join(f'{choice.nomination.title}: {choice.nominee.name}' for choice in chosen), len(chosen)])
        for choice in chosen:
            choice_rows.append([str(ballot.id), date, ballot.get_status_display(), ballot.email,
                choice.nomination.title, choice.nominee.name, str(choice.nomination_id), str(choice.nominee_id)])
    nominees = Nominee.objects.filter(nomination__contest=contest).select_related('nomination').order_by('nomination__position', 'nomination__title', 'position', 'name')
    if nomination_id:
        nominees = nominees.filter(nomination_id=nomination_id)
    # Include inactive historical projects, so old choices cannot disappear.
    result_rows = [[n.nomination.title, n.name, accepted[n.id], len(voters.get(n.nomination_id, set())), submitted] for n in nominees]
    sheets = []
    if mode in ('full', 'ballots'):
        sheets.append({'title': 'Бюллетени', 'headers': BALLOT_HEADERS, 'rows': ballot_rows})
    if mode in ('full', 'choices'):
        sheets.append({'title': 'Выбранные проекты', 'headers': CHOICE_HEADERS, 'rows': choice_rows})
    if mode in ('full', 'results'):
        sheets.append({'title': 'Итоги по проектам', 'headers': RESULT_HEADERS, 'rows': result_rows})
    return sheets, len(ballot_rows), submitted


@never_cache
@require_GET
@staff_api
@voting_api
def voting_export(request, slug, format):
    if format not in ('xlsx', 'csv'):
        raise VotingError('invalid_format', 'Поддерживаются XLSX и CSV.', status=404)
    mode = request.GET.get('mode') or 'full'
    status = request.GET.get('status') or Ballot.Status.SUBMITTED
    nomination_id = request.GET.get('nomination') or None
    if mode not in ('full', 'ballots', 'choices', 'results'):
        raise VotingError('invalid_mode', 'Некорректное представление выгрузки.')
    if status not in ('all', *Ballot.Status.values):
        raise VotingError('invalid_status', 'Некорректный статус бюллетеня.')
    with report_snapshot():
        contest = Contest.objects.filter(forum__slug=slug).first()
        if contest is None:
            raise VotingError('contest_not_found', 'Конкурс не найден.', status=404)
        if nomination_id:
            try:
                nomination_id = str(uuid.UUID(nomination_id))
            except (ValueError, TypeError, AttributeError):
                raise VotingError('invalid_nomination', 'Некорректная номинация.')
            if not contest.nominations.filter(pk=nomination_id).exists():
                raise VotingError('invalid_nomination', 'Номинация не принадлежит конкурсу.')
        sheets, total, submitted = voting_sheets(contest, mode, status, nomination_id)
    filters = {'contest': slug, 'mode': mode, 'status': status, 'nomination': nomination_id, 'format': format}
    rows = sheets[0]['rows']
    sheets.append({'title': 'О выгрузке', 'headers': ['Параметр', 'Значение'], 'rows': [
        ['Сформировано (время Томска)', timestamp()], ['Конкурс', contest.title],
        ['Фильтры', str(filters)], ['Администратор', request.user.get_username()],
        ['Бюллетеней в выгрузке', total], ['Из них принято', submitted],
        ['Учёт голосов', 'Сохранённые голоса всех раундов вместе. Итоги учитывают только принятые бюллетени.'],
        ['Люди и бюллетени', 'Голосование без почты анонимное: ФИО, телефон и e-mail не собираются. Бюллетень не равен уникальному человеку.'],
        ['Повторное голосование', 'Один человек мог проголосовать в разных раундах. Выгрузка сохраняет каждый бюллетень отдельно.'],
        ['Ожидающие подтверждения', 'Предварительный выбор не считается голосом и не включается в выбранные проекты.'],
        ['Обновление', 'Данные из базы на момент скачивания. Для обновления скачайте файл ещё раз.'],
    ]})
    filename = f'voting-{slug}-{mode}-{timezone.now():%Y%m%d-%H%M%S}.{format}'
    content = xlsx_bytes(sheets) if format == 'xlsx' else csv_bytes(sheets[0]['headers'], rows)
    log_export(request.user, 'voting', filters, filename, len(rows), request.META.get('REMOTE_ADDR'))
    return file_response(content, filename, XLSX_MIME if format == 'xlsx' else 'text/csv; charset=utf-8')
