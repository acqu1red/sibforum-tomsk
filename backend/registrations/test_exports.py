import io
from datetime import time
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from openpyxl import load_workbook

from forums.models import Event, EventDay, Forum
from voting.models import Ballot, Contest, Nomination, Nominee, VoteSelection
from .models import EmailChallenge, ExportLog, NotificationOutbox, Participant, Registration, RegistrationItem, Ticket
from .reports import csv_bytes, report_snapshot


@override_settings(SECURE_SSL_REDIRECT=False, ADMIN_TOTP_REQUIRED=False,
                   ADMIN_HOSTS=['admin.localhost'], ALLOWED_HOSTS=['admin.localhost', 'testserver'])
class ExcelExportTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.forum = Forum.objects.create(slug='promtour', title='Тестовый форум', starts_at=now, ends_at=now + timezone.timedelta(days=2), status='published')
        day = EventDay.objects.create(forum=cls.forum, date=now.date(), title='День 1')
        day2 = EventDay.objects.create(forum=cls.forum, date=now.date() + timezone.timedelta(days=1), title='День 2', position=1)
        cls.route = Event.objects.create(day=day, title='Одинаковое название', kind='route', start_time=time(9), end_time=time(11), is_paid=True, price=Decimal('2500.00'), payment_note='Оплата после звонка куратора')
        cls.seminar = Event.objects.create(day=day2, title='Одинаковое название', kind='seminar', start_time=time(12), end_time=time(13))
        cls.registrations = []
        for number in range(4):
            person = Participant.objects.create(forum=cls.forum, last_name=f'Участник {number}', first_name='Тест', email=f'test{number}@example.org', phone='79990000000', organization='=HYPERLINK("https://invalid.example")', position='Руководитель', category='business')
            cls.registrations.append(Registration.objects.create(participant=person, email_verified_at=now if number != 2 else None))
        cls.pending = RegistrationItem.objects.create(registration=cls.registrations[0], event=cls.route, status='pending_review')
        RegistrationItem.objects.create(registration=cls.registrations[0], event=cls.seminar, status='confirmed')
        RegistrationItem.objects.create(registration=cls.registrations[1], event=cls.route, status='approved')
        RegistrationItem.objects.create(registration=cls.registrations[1], event=cls.seminar, status='cancelled_by_user')
        EmailChallenge.objects.create(registration=cls.registrations[2], pending_selection=[{'event_id': str(cls.seminar.pk)}], expires_at=now)
        EmailChallenge.objects.create(registration=cls.registrations[2], pending_selection=[{'event_id': str(cls.route.pk)}], expires_at=now)
        cls.contest = Contest.objects.create(forum=cls.forum, title='Конкурс', voting_mode='simple', voting_round=2)
        cls.nomination = Nomination.objects.create(contest=cls.contest, title='Первая номинация')
        cls.other_nomination = Nomination.objects.create(contest=cls.contest, title='Другая номинация')
        cls.nominee = Nominee.objects.create(nomination=cls.nomination, name='Сохранённый исторический проект', is_active=False)
        cls.other_nominee = Nominee.objects.create(nomination=cls.other_nomination, name='Другой проект')
        cls.ballots = []
        for number, status in enumerate(('submitted', 'submitted', 'cancelled', 'pending_email')):
            ballot = Ballot.objects.create(contest=cls.contest, status=status, email='mail@example.org' if number == 1 else '', submitted_at=now if status != 'pending_email' else None, verification_expires_at=now,
                identity_hash=f'SECRET-IDENTITY-{number}', browser_hash=f'SECRET-BROWSER-{number}', network_hash=f'SECRET-NETWORK-{number}', code_hash='SECRET-CODE')
            if status != 'pending_email':
                VoteSelection.objects.create(ballot=ballot, nomination=cls.nomination, nominee=cls.nominee)
            if number == 0:
                VoteSelection.objects.create(ballot=ballot, nomination=cls.other_nomination, nominee=cls.other_nominee)
            cls.ballots.append(ballot)
        cls.admin = get_user_model().objects.create_superuser('export-director', password='test-only')

    def setUp(self):
        self.client.force_login(self.admin)

    def get(self, path, data=None):
        return self.client.get(path, data or {}, HTTP_HOST='admin.localhost')

    def registration_file(self, **filters):
        response = self.get(reverse('staff-registration-export', args=['xlsx']), filters)
        self.assertEqual(response.status_code, 200, response.content[:500])
        self.assertIn('no-store', response['Cache-Control'])
        return load_workbook(io.BytesIO(response.content), data_only=False)

    def vote_file(self, **filters):
        response = self.get(reverse('staff-voting-export', args=['promtour', 'xlsx']), filters)
        self.assertEqual(response.status_code, 200, response.content[:500])
        return load_workbook(io.BytesIO(response.content))

    def records(self, sheet):
        rows = list(sheet.values)
        return [dict(zip(rows[0], row)) for row in rows[1:]]

    def test_full_registration_file_includes_all_people_and_every_sheet(self):
        workbook = self.registration_file(mode='full')
        self.assertEqual(workbook.sheetnames, ['Участники', 'Записи на мероприятия', 'Маршруты', 'Статистика мероприятий', 'О выгрузке'])
        self.assertEqual(len(self.records(workbook['Участники'])), 4)
        self.assertEqual(len(self.records(workbook['Записи на мероприятия'])), 6)
        routes = self.records(workbook['Маршруты'])
        self.assertEqual(len(routes), 3)
        self.assertEqual({r['Тип события'] for r in routes}, {'Экскурсионный маршрут'})
        self.assertEqual(routes[0]['Цена'], 2500)
        self.assertEqual(ExportLog.objects.get().row_count, 4)
        self.assertEqual(workbook['Участники'].freeze_panes, 'A2')
        self.assertTrue(workbook['Участники'].auto_filter.ref)

    def test_event_and_status_must_match_the_same_booking_in_all_modes(self):
        for mode in ('summary', 'items', 'full'):
            with self.subTest(mode=mode):
                workbook = self.registration_file(mode=mode, event=str(self.route.pk), status='confirmed')
                self.assertEqual(workbook.worksheets[0].max_row, 1)
        workbook = self.registration_file(mode='summary', event=str(self.route.pk), status='pending_review')
        rows = self.records(workbook['Участники'])
        self.assertEqual(len(rows), 1)
        self.assertNotIn('День 2', rows[0]['События'])
        self.assertNotIn('Подтверждено', rows[0]['События'])
        self.assertEqual(rows[0]['Статусы'], 'На рассмотрении')

    def test_duplicate_titles_are_not_merged_in_statistics(self):
        workbook = self.registration_file(mode='full')
        rows = self.records(workbook['Статистика мероприятий'])
        self.assertEqual(len(rows), 2)
        self.assertEqual({r['ID события'] for r in rows}, {str(self.route.pk), str(self.seminar.pk)})
        self.assertEqual(sorted(r['Всего записей'] for r in rows), [2, 3])

    def test_unconfirmed_uses_latest_selection_and_is_not_a_booking(self):
        workbook = self.registration_file(mode='items', status='unverified')
        rows = self.records(workbook.worksheets[0])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['Тип события'], 'Экскурсионный маршрут')
        self.assertIn('предварительный', rows[0]['Статус'])
        self.assertEqual(rows[0]['Почта подтверждена'], 'Нет')
        self.assertEqual(RegistrationItem.objects.count(), 4)
        self.assertEqual(Ticket.objects.count(), 0)
        self.assertEqual(NotificationOutbox.objects.count(), 0)

    def test_routes_and_type_filters(self):
        workbook = self.registration_file(mode='routes')
        self.assertEqual(len(self.records(workbook['Маршруты'])), 3)
        workbook = self.registration_file(mode='summary', kind='seminar')
        rows = self.records(workbook['Участники'])
        self.assertEqual(len(rows), 2)
        self.assertTrue(all('12:00' in row['События'] and '09:00' not in row['События'] for row in rows))

    def test_download_reads_fresh_data_and_audits_without_modifying_business_data(self):
        first = self.registration_file(mode='items', status='approved')
        self.assertEqual(first.worksheets[0].max_row, 2)
        self.pending.status = 'approved'
        self.pending.save()
        second = self.registration_file(mode='items', status='approved')
        self.assertEqual(second.worksheets[0].max_row, 3)
        self.assertEqual(ExportLog.objects.count(), 2)
        self.assertEqual((Registration.objects.count(), RegistrationItem.objects.count(), Ballot.objects.count(), VoteSelection.objects.count()), (4, 4, 4, 4))
        self.assertEqual(NotificationOutbox.objects.count(), 0)

    def test_formula_injection_is_escaped_in_xlsx_and_csv(self):
        workbook = self.registration_file(mode='summary')
        rows = self.records(workbook['Участники'])
        self.assertTrue(rows[0]['Организация'].startswith("'=HYPERLINK"))
        self.assertTrue(rows[0]['Телефон'].startswith("'+7"))
        self.assertFalse(any(cell.data_type == 'f' for row in workbook['Участники'] for cell in row))
        content = csv_bytes(['x'], [[' =2+2'], ['@SUM(A1)'], ['+7999']]).decode('utf-8-sig')
        self.assertIn("' =2+2", content)
        self.assertIn("'@SUM", content)

    def test_voting_full_preserves_all_rounds_and_historical_projects(self):
        workbook = self.vote_file()
        self.assertEqual(workbook.sheetnames, ['Бюллетени', 'Выбранные проекты', 'Итоги по проектам', 'О выгрузке'])
        rows = self.records(workbook['Бюллетени'])
        self.assertEqual(len(rows), 2)
        self.assertEqual({r['ID бюллетеня'] for r in rows}, {str(b.id) for b in self.ballots[:2]})
        self.assertEqual(sum(bool(r['E-mail (если указан)']) for r in rows), 1)
        self.assertEqual(len(self.records(workbook['Выбранные проекты'])), 3)
        results = self.records(workbook['Итоги по проектам'])
        self.assertEqual(next(r for r in results if r['Проект / компания'] == self.nominee.name)['Принято голосов'], 2)
        self.assertEqual(Ballot.objects.count(), 4)
        for sheet in workbook:
            self.assertNotIn('SECRET-', str(list(sheet.values)))
        self.assertNotIn('ФИО', next(iter(workbook['Бюллетени'].values)))

    def test_voting_statuses_and_nomination_filter(self):
        workbook = self.vote_file(status='all', mode='full')
        self.assertEqual(len(self.records(workbook['Бюллетени'])), 4)
        self.assertEqual(sum(r['Принято голосов'] for r in self.records(workbook['Итоги по проектам'])), 3)
        workbook = self.vote_file(nomination=str(self.other_nomination.pk))
        self.assertEqual(len(self.records(workbook['Бюллетени'])), 1)
        self.assertEqual(len(self.records(workbook['Выбранные проекты'])), 1)
        workbook = self.vote_file(status='pending_email', mode='ballots')
        self.assertEqual(len(self.records(workbook['Бюллетени'])), 1)
        self.assertEqual(self.records(workbook['Бюллетени'])[0]['Число выбранных проектов'], 0)

    def test_voting_modes_and_csv_have_correct_first_sheet(self):
        for mode, title in [('ballots', 'Бюллетени'), ('choices', 'Выбранные проекты'), ('results', 'Итоги по проектам')]:
            with self.subTest(mode=mode):
                self.assertEqual(self.vote_file(mode=mode).sheetnames, [title, 'О выгрузке'])
        response = self.get(reverse('staff-voting-export', args=['promtour', 'csv']), {'mode': 'choices'})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'\xef\xbb\xbf'))

    def test_invalid_filters_are_rejected_and_not_audited(self):
        other = Forum.objects.create(slug='other', title='Другой форум', starts_at=timezone.now(), ends_at=timezone.now())
        day = EventDay.objects.create(forum=other, title='Другой день', date=timezone.now().date())
        event = Event.objects.create(day=day, title='Чужое событие', start_time=time(10), end_time=time(11))
        for filters in ({'event': 'bad'}, {'event': str(event.id)}, {'status': 'bad'}, {'mode': 'bad'}, {'kind': 'bad'}):
            self.assertEqual(self.get(reverse('staff-registration-export', args=['xlsx']), filters).status_code, 422)
        for filters in ({'nomination': 'bad'}, {'nomination': str(event.id)}, {'status': 'bad'}, {'mode': 'bad'}):
            self.assertEqual(self.get(reverse('staff-voting-export', args=['promtour', 'xlsx']), filters).status_code, 422)
        self.assertFalse(ExportLog.objects.exists())

    def test_hub_and_downloads_obey_separate_permissions(self):
        reg_url = reverse('staff-registration-export', args=['xlsx'])
        vote_url = reverse('staff-voting-export', args=['promtour', 'xlsx'])
        for label, permission, allowed, forbidden, expected, hidden in [
            ('registration', 'view_registration', reg_url, vote_url, 'registration-exports', 'voting-exports'),
            ('contest', 'view_contest', vote_url, reg_url, 'voting-exports', 'registration-exports'),
        ]:
            with self.subTest(role=label):
                user = get_user_model().objects.create_user(label, is_staff=True)
                user.user_permissions.add(Permission.objects.get(codename=permission))
                self.client.force_login(user)
                response = self.get('/admin/exports/')
                self.assertContains(response, f'id="{expected}"')
                self.assertNotContains(response, f'id="{hidden}"')
                self.assertEqual(self.get(allowed).status_code, 200)
                self.assertEqual(self.get(forbidden).status_code, 403)
                self.assertContains(self.get('/admin/'), 'Выгрузки Excel')
        user = get_user_model().objects.create_user('no-reports', is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.get('/admin/exports/').status_code, 403)
        self.client.logout()
        self.assertEqual(self.get(vote_url).status_code, 401)
        self.assertEqual(self.get(reg_url).status_code, 401)

    def test_downloads_require_admin_host_and_second_factor_when_enabled(self):
        url = reverse('staff-voting-export', args=['promtour', 'xlsx'])
        self.assertEqual(self.client.get(url, HTTP_HOST='testserver').status_code, 404)
        with override_settings(ADMIN_TOTP_REQUIRED=True):
            self.assertEqual(self.get(url).status_code, 302)
        self.assertEqual(self.client.post(url, HTTP_HOST='admin.localhost').status_code, 405)

    def test_old_registration_download_url_still_works(self):
        self.assertEqual(self.get('/admin/exports/', {'mode': 'summary', 'format': 'xlsx'}).status_code, 200)
        self.assertEqual(self.get(reverse('admin-registration-export', args=['xlsx'])).status_code, 200)

    def test_empty_workbooks_are_valid(self):
        RegistrationItem.objects.all().delete()
        EmailChallenge.objects.all().delete()
        workbook = self.registration_file(mode='routes')
        self.assertEqual(workbook['Маршруты'].max_row, 1)
        Ballot.objects.all().delete()
        workbook = self.vote_file()
        self.assertEqual(workbook['Бюллетени'].max_row, 1)
        self.assertEqual(sum(r['Принято голосов'] for r in self.records(workbook['Итоги по проектам'])), 0)


class ReportSnapshotTests(TransactionTestCase):
    def test_postgres_snapshot_is_read_only_then_returns_to_writable(self):
        if connection.vendor != 'postgresql':
            self.skipTest('PostgreSQL snapshot isolation')
        with report_snapshot():
            with connection.cursor() as cursor:
                cursor.execute('SHOW transaction_isolation')
                self.assertEqual(cursor.fetchone()[0], 'repeatable read')
                cursor.execute('SHOW transaction_read_only')
                self.assertEqual(cursor.fetchone()[0], 'on')
        with connection.cursor() as cursor:
            cursor.execute('SHOW transaction_read_only')
            self.assertEqual(cursor.fetchone()[0], 'off')
