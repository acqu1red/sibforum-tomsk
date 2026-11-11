import json
from functools import wraps

from django.http import JsonResponse
from django.db.models import Prefetch
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.csrf import csrf_protect
from django.middleware.csrf import get_token
import secrets
from django.views.decorators.http import require_GET, require_POST

from forums.security import client_ip
from forums.media import public_asset
from registrations.reports import XLSX_MIME, csv_bytes, file_response, log_export, timestamp, xlsx_bytes
from .models import Contest, Nomination, Nominee
from .workflow import VotingError, check_rate_limit, stats_payload, submit_ballot, verify_ballot
from .simple import browser_identity, set_browser_cookie, submit_simple, voter_status


def json_response(data, status=200):
    return JsonResponse(data, status=status, json_dumps_params={'ensure_ascii': False})


def parse_json(request):
    length = int(request.headers.get('Content-Length') or 0)
    if length <= 0 or length > 64 * 1024:
        raise VotingError('bad_request', 'Некорректный размер запроса.', status=400)
    try:
        payload = json.loads(request.body.decode('utf-8'))
    except (ValueError, UnicodeDecodeError):
        raise VotingError('bad_request', 'Некорректный JSON.', status=400)
    if not isinstance(payload, dict):
        raise VotingError('bad_request', 'Ожидался JSON-объект.', status=400)
    return payload


def voting_api(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except VotingError as error:
            return json_response({'ok': False, 'error': error.code, 'message': error.message}, status=error.status)
    return wrapped


def staff_api(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return json_response({'ok': False, 'error': 'authentication_required'}, status=401)
        if not request.user.is_staff:
            return json_response({'ok': False, 'error': 'permission_denied'}, status=403)
        if not request.user.has_perm('voting.view_contest'):
            return json_response({'ok': False, 'error': 'permission_denied'}, status=403)
        return view(request, *args, **kwargs)
    return wrapped


def contest_by_slug(slug, catalog=False):
    queryset = Contest.objects.filter(forum__slug=slug, forum__status='published')
    if catalog:
        queryset = queryset.prefetch_related(Prefetch(
            'nominations', queryset=Nomination.objects.filter(is_active=True).prefetch_related(
                Prefetch('nominees', queryset=Nominee.objects.filter(is_active=True).prefetch_related('photos'), to_attr='public_nominees')
            ), to_attr='public_nominations',
        ))
    contest = queryset.first()
    if not contest:
        raise VotingError('contest_not_found', 'Конкурс не найден.', status=404)
    return contest


def contest_payload(contest):
    payload = {
        'title': contest.title,
        'description': contest.description,
        'rules_text': contest.rules_text,
        'voting_mode': contest.voting_mode,
        'is_open': contest.is_open,
        'voting_opens_at': contest.voting_opens_at.isoformat() if contest.voting_opens_at else None,
        'voting_closes_at': contest.voting_closes_at.isoformat() if contest.voting_closes_at else None,
        'results_published': contest.results_published,
        'winners_text': contest.winners_text,
        'nominations': [],
    }
    for nomination in contest.public_nominations:
        payload['nominations'].append({
            'id': str(nomination.id),
            'title': nomination.title,
            'description': nomination.description,
            'selection_hint': nomination.selection_hint,
            'visual_group': nomination.visual_group,
            'min_selections': nomination.min_selections,
            'max_selections': nomination.max_selections,
            'nominees': [
                {
                    'id': str(nominee.id),
                    'name': nominee.name,
                    'description': nominee.description,
                    'website_url': nominee.website_url,
                    'logo': nominee.logo_variants.get('400') or (nominee.logo.url if nominee.logo else public_asset(nominee.static_logo)),
                    'photos': [{'url': p.variants.get('960') or p.image.url, 'thumbnail': p.variants.get('160') or p.image.url, 'caption': p.caption} for p in nominee.photos.all()],
                }
                for nominee in nomination.public_nominees
            ],
        })
    if contest.results_published:
        payload['stats'] = stats_payload(contest)
    return payload


@never_cache
@require_GET
@voting_api
def contest_detail(request, slug):
    return json_response(contest_payload(contest_by_slug(slug, catalog=True)))


@require_GET
@voting_api
def contest_results(request, slug):
    contest = contest_by_slug(slug)
    if not contest.results_published:
        raise VotingError('results_not_published', 'Итоги ещё не опубликованы.', status=404)
    return json_response(stats_payload(contest))


@csrf_protect
@require_POST
@voting_api
def submit(request, slug):
    contest = contest_by_slug(slug)
    payload = parse_json(request)
    ip_address = client_ip(request)
    check_rate_limit(ip_address, 'submit')
    if contest.voting_mode == 'simple':
        ballot = submit_simple(contest, browser_identity(request), ip_address, payload.get('selections'))
        return json_response({'ok': True, 'status': 'submitted', 'ballot_id': str(ballot.id), 'submitted_at': ballot.submitted_at.isoformat()})
    result = submit_ballot(
        contest,
        payload.get('email'),
        payload.get('selections'),
        captcha_token=payload.get('captcha_token'),
        ip_address=ip_address,
    )
    return json_response(result)


@never_cache
@require_GET
@voting_api
def voter_session(request, slug):
    contest = contest_by_slug(slug)
    browser = browser_identity(request) or secrets.token_hex(32)
    response = json_response({'csrf_token': get_token(request), 'already_voted': voter_status(contest, browser, client_ip(request)) if contest.voting_mode == 'simple' else False})
    set_browser_cookie(response, browser)
    return response


@csrf_exempt
@require_POST
@voting_api
def verify(request, slug):
    contest = contest_by_slug(slug)
    payload = parse_json(request)
    check_rate_limit(client_ip(request), 'verify')
    ballot = verify_ballot(contest, payload.get('email'), payload.get('code'))
    return json_response({'ok': True, 'status': 'submitted', 'ballot_id': str(ballot.id), 'submitted_at': ballot.submitted_at.isoformat()})


@never_cache
@require_GET
@staff_api
@voting_api
def admin_stats(request, slug):
    return json_response(stats_payload(contest_by_slug(slug)))


def voting_export_rows(contest):
    stats = stats_payload(contest)
    headers = ['Номинация', 'Визуальная группа', 'Кандидат', 'Голоса', 'Пропущено бюллетеней', 'Всего бюллетеней']
    rows = []
    for nomination in stats['nominations']:
        for nominee in nomination['nominees']:
            rows.append([nomination['title'], nomination['visual_group'], nominee['name'], nominee['votes'], nomination['skipped'], stats['total_ballots']])
    return headers, rows, stats['total_ballots']


@never_cache
@require_GET
@staff_api
@voting_api
def admin_export(request, slug):
    contest = contest_by_slug(slug)
    headers, rows, total = voting_export_rows(contest)
    filename = f'voting-{slug}.csv'
    log_export(request.user, 'voting', {'contest': slug, 'format': 'csv'}, filename, len(rows), client_ip(request))
    return file_response(csv_bytes(headers, rows), filename, 'text/csv; charset=utf-8')


@never_cache
@require_GET
@staff_api
@voting_api
def admin_export_xlsx(request, slug):
    contest = contest_by_slug(slug)
    headers, rows, total = voting_export_rows(contest)
    sheets = [
        {'title': 'По номинациям', 'headers': headers, 'rows': rows},
        {'title': 'Метаданные', 'headers': ['Параметр', 'Значение'], 'rows': [
            ['Сформировано', timestamp()],
            ['Конкурс', contest.title],
            ['Всего бюллетеней', total],
            ['Администратор', request.user.get_username()],
        ]},
    ]
    filename = f'voting-{slug}.xlsx'
    log_export(request.user, 'voting', {'contest': slug, 'format': 'xlsx'}, filename, len(rows), client_ip(request))
    return file_response(xlsx_bytes(sheets), filename, XLSX_MIME)
