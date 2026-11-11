from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless

from django.db import close_old_connections, connection, connections
from django.test import TransactionTestCase
from django.utils import timezone

from forums.models import Forum
from .models import Ballot, Contest, Nomination, Nominee
from .simple import submit_simple
from .workflow import VotingError


@skipUnless(connection.vendor == 'postgresql', 'The concurrency contract is verified against production PostgreSQL.')
class PostgreSQLBallotConcurrencyTests(TransactionTestCase):
    def setUp(self):
        now = timezone.now()
        forum = Forum.objects.create(slug='race', title='Форум', starts_at=now, ends_at=now+timezone.timedelta(days=1), status='published')
        self.contest = Contest.objects.create(forum=forum, title='Голосование', voting_mode='simple', is_open=True)
        nomination = Nomination.objects.create(contest=self.contest, title='Номинация')
        candidate = Nominee.objects.create(nomination=nomination, name='Кандидат')
        self.selection = [{'nomination_id':str(nomination.pk), 'nominee_ids':[str(candidate.pk)]}]

    def test_parallel_requests_from_one_network_save_exactly_one_ballot(self):
        def vote(index):
            close_old_connections()
            try:
                submit_simple(self.contest, f'{index:064x}', '192.0.2.45', self.selection)
                return 'accepted'
            except VotingError as error:
                return error.code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(vote, range(8)))
        self.assertEqual(results.count('accepted'), 1)
        self.assertEqual(results.count('already_voted'), 7)
        self.assertEqual(Ballot.objects.filter(status='submitted').count(), 1)
