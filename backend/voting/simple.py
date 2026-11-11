"""Anonymous ballots: no forum account, no SMS, bounded network/browser repeats."""
import ipaddress
import secrets

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Ballot, Contest, VoteResetLog, VoteSelection
from .workflow import VotingError, ensure_voting_open, identity_hash, normalize_selection


COOKIE_NAME = 'forum_voter'
COOKIE_SALT = 'sibforum-voter-v1'


def network_identity(ip):
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        raise VotingError('network_unavailable', 'Не удалось проверить сеть. Обновите страницу.', status=400)
    network = str(ipaddress.ip_network(f'{address}/64', strict=False)) if address.version == 6 else str(address)
    return identity_hash('network:' + network)


def browser_identity(request):
    value = request.get_signed_cookie(COOKIE_NAME, default='', salt=COOKIE_SALT, max_age=366*86400)
    return value if len(value) == 64 else ''


def set_browser_cookie(response, value):
    response.set_signed_cookie(COOKIE_NAME, value, salt=COOKIE_SALT, max_age=366*86400,
                               httponly=True, secure=settings.SESSION_COOKIE_SECURE,
                               samesite='Lax', path='/')


def voter_status(contest, browser, ip):
    network = network_identity(ip)
    existing = contest.ballots.filter(status=Ballot.Status.SUBMITTED)
    return existing.filter(browser_hash=identity_hash('browser:' + browser)).exists() or existing.filter(network_hash=network).count() >= contest.max_ballots_per_network


def submit_simple(contest, browser, ip, selections):
    if not browser:
        raise VotingError('session_required', 'Обновите страницу, чтобы начать голосование.', status=409)
    try:
        with transaction.atomic():
            # Serialize only the short write transaction; catalog reads remain concurrent.
            contest = Contest.objects.select_for_update().get(pk=contest.pk)
            ensure_voting_open(contest)
            if contest.voting_mode != 'simple':
                raise VotingError('mode_changed', 'Способ голосования изменился. Обновите страницу.', status=409)
            network = network_identity(ip)
            browser_hash = identity_hash('browser:' + browser)
            existing = contest.ballots.filter(status=Ballot.Status.SUBMITTED)
            if existing.filter(browser_hash=browser_hash).exists():
                raise VotingError('already_voted', 'С этого браузера уже принят бюллетень. Спасибо за участие.', status=409)
            slots = set(existing.filter(network_hash=network).values_list('network_slot', flat=True))
            slot = next((i for i in range(contest.max_ballots_per_network) if i not in slots), None)
            if slot is None:
                raise VotingError('already_voted', 'С этой сети уже принято допустимое количество бюллетеней. Повторное голосование ограничено.', status=409)
            normalized = normalize_selection(contest, selections)
            if not any(s['nominees'] for s in normalized):
                raise VotingError('selection_required', 'Выберите хотя бы одного кандидата в любой номинации.')
            now = timezone.now()
            ballot = Ballot.objects.create(contest=contest, email='', identity_hash=browser_hash,
                network_hash=network, browser_hash=browser_hash, network_slot=slot,
                code_hash='', verification_expires_at=now, submitted_at=now, status=Ballot.Status.SUBMITTED)
            VoteSelection.objects.bulk_create([
                VoteSelection(ballot=ballot, nomination=s['nomination'], nominee=n)
                for s in normalized for n in s['nominees']
            ])
            return ballot
    except IntegrityError as error:
        raise VotingError('already_voted', 'Бюллетень уже принят. Повторный голос не зарегистрирован.', status=409) from error


@transaction.atomic
def reset_ballots(*, contest, ballots, actor, reason):
    if not (actor.is_active and actor.is_superuser and actor.get_username() == settings.ADMIN_OWNER_USERNAME):
        from django.core.exceptions import PermissionDenied
        raise PermissionDenied('Сброс голосов доступен только руководителю.')
    if not reason.strip():
        raise VotingError('reason_required', 'Укажите причину сброса.')
    Contest.objects.select_for_update().get(pk=contest.pk)
    selected = list(ballots.select_for_update().filter(contest=contest, status=Ballot.Status.SUBMITTED))
    ids = [str(b.pk) for b in selected]
    if ids:
        Ballot.objects.filter(pk__in=ids).update(status=Ballot.Status.CANCELLED, updated_at=timezone.now())
        VoteResetLog.objects.create(contest=contest, actor=actor, reason=reason.strip(), ballot_ids=ids)
        from forums.models import ContentRevision
        import uuid
        ContentRevision.objects.update_or_create(pk=1, defaults={'token': uuid.uuid4()})
    return len(ids)
