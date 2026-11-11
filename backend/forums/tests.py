from datetime import time

from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from forums.models import Event, EventDay, EventSpeaker, Forum, Speaker
from voting.models import Contest, Nomination, Nominee


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class PublicCatalogQueriesTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        forum = Forum.objects.create(slug='audit', title='Форум', series='promtour',
                                     starts_at=now, ends_at=now + timezone.timedelta(days=1), status='published')
        day = EventDay.objects.create(forum=forum, date=now.date(), title='Программа')
        contest = Contest.objects.create(forum=forum, title='Конкурс')
        for i in range(12):
            event = Event.objects.create(day=day, title=f'Событие {i}', slug=f'event-{i}',
                                         kind='session', start_time=time(10), end_time=time(11),
                                         is_published=True)
            speaker = Speaker.objects.create(forum=forum, full_name=f'Спикер {i}', is_published=True)
            EventSpeaker.objects.create(event=event, speaker=speaker)
            nomination = Nomination.objects.create(contest=contest, title=f'Номинация {i}')
            Nominee.objects.create(nomination=nomination, name=f'Кандидат {i}')
            Nominee.objects.create(nomination=nomination, name='Скрытый кандидат', is_active=False)
        hidden = Event.objects.create(day=day, title='Скрытое событие', slug='hidden',
                                      kind='session', start_time=time(11), end_time=time(12))
        EventSpeaker.objects.create(event=hidden, speaker=speaker)
        speaker = Speaker.objects.create(forum=forum, full_name='Скрытый спикер', is_published=False)
        EventSpeaker.objects.create(event=event, speaker=speaker)
        Nomination.objects.create(contest=contest, title='Скрытая номинация', is_active=False)

    def test_program_is_bounded_and_never_reveals_unpublished_content(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/api/v1/forums/audit/program/')
        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(len(queries), 17)
        data = response.json()
        self.assertEqual(len(data['speakers']), 12)
        self.assertEqual(len(data['days'][0]['events']), 12)
        self.assertNotIn('Скрыт', response.content.decode())

    def test_contest_queries_do_not_grow_with_nomination_count(self):
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get('/api/v1/contests/audit/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(queries), 4)
        self.assertEqual(len(response.json()['nominations']), 12)
        self.assertTrue(all(len(n['nominees']) == 1 for n in response.json()['nominations']))
        self.assertNotIn('Скрыт', response.content.decode())
