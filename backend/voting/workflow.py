import hashlib
import hmac
import secrets
import uuid

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from forums.security import check_captcha
from registrations.selection import RegistrationError
from registrations.workflow import queue_notification
from .models import Ballot, VoteAttemptLog, VoteSelection


class VotingError(Exception):
    def __init__(self, code, message, status=422):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def identity_hash(email):
    return hmac.new(settings.SECRET_KEY.encode(), email.encode(), hashlib.sha256).hexdigest()


def check_rate_limit(ip_address, action):
    if not ip_address:
        return
    threshold = timezone.now() - timezone.timedelta(minutes=10)
    if VoteAttemptLog.objects.filter(ip_address=ip_address, created_at__gte=threshold).count() >= 20:
        raise VotingError('rate_limited', 'Слишком много попыток. Повторите через 10 минут.', status=429)
    VoteAttemptLog.objects.create(ip_address=ip_address, action=action)


def normalize_email(value):
    email = str(value or '').strip().lower()
    try:
        validate_email(email)
    except ValidationError:
        raise VotingError('invalid_email', 'Проверьте адрес электронной почты.')
    return email


def normalize_selection(contest, selections):
    if not isinstance(selections, list):
        raise VotingError('invalid_selection', 'Некорректный формат выбора.')
    nominations = {str(nomination.id): nomination for nomination in contest.nominations.filter(is_active=True).prefetch_related('nominees')}
    normalized = []
    seen_nominations = set()
    total = 0
    for selection in selections:
        if not isinstance(selection, dict):
            raise VotingError('invalid_selection', 'Некорректный формат номинации.')
        try:
            nomination_id = str(uuid.UUID(str(selection.get('nomination_id') or '')))
        except (ValueError, TypeError, AttributeError):
            raise VotingError('unknown_nomination', 'Некорректная номинация.')
        if nomination_id in seen_nominations:
            raise VotingError('duplicate_nomination', 'Одна номинация отправлена несколько раз.')
        seen_nominations.add(nomination_id)
        nomination = nominations.get(nomination_id)
        if not nomination:
            raise VotingError('unknown_nomination', 'Номинация недоступна для голосования.', status=404)
        nominee_ids = selection.get('nominee_ids') or []
        if not isinstance(nominee_ids, list):
            raise VotingError('invalid_selection', 'Некорректный список кандидатов.')
        try:
            nominee_ids = [str(uuid.UUID(str(nominee_id))) for nominee_id in nominee_ids]
        except (ValueError, TypeError, AttributeError):
            raise VotingError('unknown_nominee', 'Некорректный кандидат.')
        if len(nominee_ids) != len(set(nominee_ids)):
            raise VotingError('duplicate_nominee', 'Один кандидат выбран несколько раз в номинации.')
        if len(nominee_ids) < nomination.min_selections or len(nominee_ids) > nomination.max_selections:
            raise VotingError('nomination_limit', f'В номинации «{nomination.title}» допустимо от {nomination.min_selections} до {nomination.max_selections} кандидатов.')
        nominees = list(nomination.nominees.filter(is_active=True, id__in=nominee_ids))
        if len(nominees) != len(nominee_ids):
            raise VotingError('unknown_nominee', 'Один из кандидатов недоступен.', status=404)
        normalized.append({'nomination': nomination, 'nominees': nominees})
        total += len(nominees)
    if total == 0:
        raise VotingError('empty_ballot', 'Выберите хотя бы одного кандидата в любой номинации.')
    return normalized


def ensure_voting_open(contest):
    now = timezone.now()
    if not contest.is_open:
        raise VotingError('voting_closed', 'Голосование закрыто.', status=409)
    if contest.voting_opens_at and now < contest.voting_opens_at:
        raise VotingError('voting_not_started', 'Голосование ещё не началось.', status=409)
    if contest.voting_closes_at and now > contest.voting_closes_at:
        raise VotingError('voting_closed', 'Голосование уже завершено.', status=409)


@transaction.atomic
def submit_ballot(contest, email, selections, captcha_token=None, ip_address=None):
    ensure_voting_open(contest)
    try:
        check_captcha(captcha_token, ip_address)
    except RegistrationError as error:
        raise VotingError(error.code, error.message, status=error.status) from error
    email = normalize_email(email)
    normalized = normalize_selection(contest, selections)
    ballot = contest.ballots.select_for_update().filter(email=email).first()
    if ballot and ballot.status == Ballot.Status.SUBMITTED:
        raise VotingError('already_voted', 'Бюллетень с этого адреса уже принят.', status=409)
    code = f'{secrets.randbelow(1000000):06d}'
    if ballot is None:
        ballot = Ballot(contest=contest, email=email, identity_hash=identity_hash(email))
    ballot.code_hash = make_password(code)
    ballot.pending_selection = selections
    ballot.verification_expires_at = timezone.now() + timezone.timedelta(minutes=20)
    ballot.verification_attempts = 0
    ballot.status = Ballot.Status.PENDING_EMAIL
    ballot.save()
    queue_notification(
        None,
        'voting_verification',
        email,
        {'code': code, 'contest': contest.title},
        f'voting-verification:{ballot.id}',
    )
    result = {'ok': True, 'status': 'verification_required', 'delivery': 'queued', 'expires_at': ballot.verification_expires_at.isoformat()}
    if settings.DEBUG:
        result['debug_code'] = code
    return result


@transaction.atomic
def complete_ballot_verification(ballot_id, code):
    ballot = Ballot.objects.select_for_update().select_related('contest').get(id=ballot_id)
    if ballot.status == Ballot.Status.SUBMITTED:
        raise VotingError('already_voted', 'Бюллетень уже принят.', status=409)
    if ballot.verification_attempts > 5 or ballot.verification_expires_at <= timezone.now() or not check_password(code, ballot.code_hash):
        raise VotingError('invalid_code', 'Код недействителен или истёк.')
    normalized = normalize_selection(ballot.contest, ballot.pending_selection)
    now = timezone.now()
    ballot.selections.all().delete()
    for selection in normalized:
        for nominee in selection['nominees']:
            VoteSelection.objects.create(ballot=ballot, nomination=selection['nomination'], nominee=nominee)
    ballot.email_verified_at = now
    ballot.submitted_at = now
    ballot.status = Ballot.Status.SUBMITTED
    ballot.pending_selection = []
    ballot.save()
    selected_names = [nominee.name for selection in normalized for nominee in selection['nominees']]
    queue_notification(
        None,
        'voting_confirmation',
        ballot.email,
        {'contest': ballot.contest.title, 'selected': selected_names},
        f'voting-confirmation:{ballot.id}',
    )
    return ballot


def verify_ballot(contest, email, code):
    email = normalize_email(email)
    ballot = contest.ballots.filter(email=email).first()
    if ballot and ballot.status == Ballot.Status.SUBMITTED:
        raise VotingError('already_voted', 'Бюллетень уже принят.', status=409)
    if not ballot or ballot.verification_attempts >= 5 or ballot.verification_expires_at <= timezone.now():
        raise VotingError('invalid_code', 'Код недействителен или истёк.')
    ballot.verification_attempts += 1
    ballot.save(update_fields=('verification_attempts', 'updated_at'))
    if not check_password(str(code or ''), ballot.code_hash):
        raise VotingError('invalid_code', 'Код недействителен или истёк.')
    return complete_ballot_verification(ballot.id, str(code or ''))


def stats_payload(contest):
    ballots = contest.ballots.filter(status=Ballot.Status.SUBMITTED)
    total = ballots.count()
    nominations = []
    for nomination in contest.nominations.filter(is_active=True).prefetch_related('nominees'):
        selections = VoteSelection.objects.filter(ballot__in=ballots, nomination=nomination)
        voted_ballots = selections.values('ballot').distinct().count()
        nominees = []
        for nominee in nomination.nominees.filter(is_active=True):
            nominees.append({
                'id': str(nominee.id),
                'name': nominee.name,
                'votes': selections.filter(nominee=nominee).count(),
            })
        nominees.sort(key=lambda item: (-item['votes'], item['name']))
        nominations.append({
            'id': str(nomination.id),
            'title': nomination.title,
            'visual_group': nomination.visual_group,
            'total_voters': voted_ballots,
            'skipped': total - voted_ballots,
            'nominees': nominees,
        })
    return {'total_ballots': total, 'nominations': nominations}
