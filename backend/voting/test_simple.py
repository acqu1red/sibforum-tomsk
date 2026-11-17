import json
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from forums.models import Forum
from .models import Ballot, Contest, Nomination, Nominee, VoteResetLog
from .simple import reset_ballots
from .workflow import stats_payload


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'], SESSION_COOKIE_SECURE=False)
class SimpleVotingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        forum = Forum.objects.create(slug='simple', title='Форум', starts_at=now, ends_at=now+timezone.timedelta(days=1), status='published')
        cls.contest = Contest.objects.create(forum=forum, title='Конкурс', is_open=True, voting_mode='simple')
        cls.nomination = Nomination.objects.create(contest=cls.contest, title='Номинация', max_selections=1)
        cls.a = Nominee.objects.create(nomination=cls.nomination, name='Альфа')
        cls.b = Nominee.objects.create(nomination=cls.nomination, name='Бета')

    def session(self, client=None, ip='192.0.2.1'):
        client = client or self.client
        return client.get('/api/v1/contests/simple/voter-session/', REMOTE_ADDR=ip).json()['csrf_token']

    def vote(self, client=None, ip='192.0.2.1', ids=None, csrf=''):
        return (client or self.client).post('/api/v1/contests/simple/ballots/', data=json.dumps({'selections':[{'nomination_id':str(self.nomination.pk),'nominee_ids':ids or [str(self.a.pk)]}]}), content_type='application/json', REMOTE_ADDR=ip, HTTP_X_CSRFTOKEN=csrf)

    def test_anonymous_vote_is_atomic_and_repeats_are_rejected(self):
        self.session()
        result = self.vote()
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['status'], 'submitted')
        self.assertEqual(self.vote(ip='192.0.2.2').status_code, 409)
        new = Client(); self.session(new)
        self.assertEqual(self.vote(new).status_code, 409)
        self.assertEqual(Ballot.objects.filter(status='submitted').count(), 1)
        ballot = Ballot.objects.get()
        self.assertEqual(ballot.email, '')
        self.assertEqual(ballot.selections.count(), 1)
        self.assertNotIn('192.0.2.1', ballot.network_hash)

    def test_csrf_and_session_are_required(self):
        secure = Client(enforce_csrf_checks=True)
        self.assertEqual(self.vote(secure).status_code, 403)
        csrf = self.session(secure)
        self.assertEqual(self.vote(secure, csrf=csrf).status_code, 200)

    def test_limit_and_closed_contest_never_save_ballots(self):
        self.session()
        self.assertEqual(self.vote(ids=[str(self.a.pk), str(self.b.pk)]).status_code, 422)
        self.contest.is_open = False; self.contest.save()
        self.assertEqual(self.vote().status_code, 409)
        self.assertFalse(Ballot.objects.exists())

    def test_database_constraint_prevents_duplicate_network_even_outside_workflow(self):
        self.session(); self.vote(); ballot = Ballot.objects.get()
        with self.assertRaises(IntegrityError), transaction.atomic():
            Ballot.objects.create(contest=self.contest, email='', identity_hash='another', network_hash=ballot.network_hash, browser_hash='different', network_slot=0, code_hash='', verification_expires_at=timezone.now(), status='submitted')

    def test_only_director_resets_with_history_and_releases_repeat_limit(self):
        self.session(); self.vote()
        user = get_user_model().objects.create_user('another-root', is_staff=True, is_superuser=True)
        with self.assertRaises(PermissionDenied):
            reset_ballots(contest=self.contest, ballots=Ballot.objects.all(), actor=user, reason='Тест')
        owner = get_user_model().objects.create_user('director', is_staff=True, is_superuser=True)
        self.assertEqual(reset_ballots(contest=self.contest, ballots=Ballot.objects.all(), actor=owner, reason='Проверка до рассылки'), 1)
        self.assertEqual(stats_payload(self.contest)['total_ballots'], 0)
        self.assertEqual(VoteResetLog.objects.count(), 1)
        self.assertEqual(self.vote().status_code, 200)
        self.assertEqual(Ballot.objects.filter(status='cancelled').count(), 1)

    def test_content_changes_never_reset_votes(self):
        self.session(); self.vote()
        self.a.description='Новые фотографии'; self.a.save()
        Nominee.objects.create(nomination=self.nomination, name='Гамма')
        self.assertEqual(stats_payload(self.contest)['total_ballots'], 1)
        self.assertEqual(self.vote().status_code, 409)

    def test_shared_network_allows_distinct_browsers_but_never_the_same_browser_twice(self):
        self.contest.max_ballots_per_network=0;self.contest.save()
        self.session()
        self.assertEqual(self.vote().status_code,200)
        other=Client()
        session=other.get('/api/v1/contests/simple/voter-session/',REMOTE_ADDR='192.0.2.1').json()
        self.assertFalse(session['already_voted'])
        self.assertEqual(self.vote(other).status_code,200)
        self.assertEqual(self.vote(ip='192.0.2.2').status_code,409)
        self.assertTrue(self.client.get('/api/v1/contests/simple/voter-session/',REMOTE_ADDR='192.0.2.2').json()['already_voted'])
        self.assertEqual(Ballot.objects.filter(status='submitted').count(),2)
        self.assertEqual(set(Ballot.objects.values_list('network_slot',flat=True)),{0,1})

    def test_shared_network_continues_after_preexisting_network_ballot(self):
        self.session();self.assertEqual(self.vote().status_code,200)
        previous=list(Ballot.objects.values('pk','identity_hash','network_hash','network_slot','status'))
        self.contest.max_ballots_per_network=0;self.contest.save()
        other=Client();self.session(other)
        self.assertEqual(self.vote(other).status_code,200)
        self.assertEqual(list(Ballot.objects.filter(pk=previous[0]['pk']).values('pk','identity_hash','network_hash','network_slot','status')),previous)

    def test_new_round_allows_exactly_one_more_vote_and_preserves_previous_results(self):
        self.contest.max_ballots_per_network=0;self.contest.save()
        self.session();self.assertEqual(self.vote().status_code,200)
        first=Ballot.objects.get()
        old_fields={f.name:getattr(first,f.attname) for f in first._meta.concrete_fields}
        old_selection=list(first.selections.values())
        cookie=self.client.cookies['forum_voter'].value
        self.assertEqual(self.vote().status_code,409)
        self.contest.voting_round=2;self.contest.save()
        session=self.client.get('/api/v1/contests/simple/voter-session/',REMOTE_ADDR='192.0.2.1').json()
        self.assertFalse(session['already_voted'])
        self.assertEqual(self.client.cookies['forum_voter'].value.split(':')[0],cookie.split(':')[0])
        self.assertEqual(self.vote().status_code,200)
        self.assertEqual(self.vote(ip='192.0.2.2').status_code,409)
        self.assertEqual(Ballot.objects.filter(status='submitted').count(),2)
        first.refresh_from_db()
        self.assertEqual({f.name:getattr(first,f.attname) for f in first._meta.concrete_fields},old_fields)
        self.assertEqual(list(first.selections.values()),old_selection)
        stats=stats_payload(self.contest)
        self.assertEqual(stats['total_ballots'],2)
        votes={entry['id']:entry['votes'] for entry in stats['nominations'][0]['nominees']}
        self.assertEqual(votes[str(self.a.pk)],2)

    def test_network_limits_are_scoped_to_round_without_changing_legacy_hashes(self):
        self.session();self.assertEqual(self.vote().status_code,200)
        first=Ballot.objects.get()
        self.contest.voting_round=2;self.contest.save()
        self.assertEqual(self.vote().status_code,200)
        self.assertEqual(self.vote().status_code,409)
        self.assertEqual(Ballot.objects.count(),2)
        new=Ballot.objects.exclude(pk=first.pk).get()
        self.assertNotEqual(first.network_hash,new.network_hash)
        self.assertNotEqual(first.browser_hash,new.browser_hash)
