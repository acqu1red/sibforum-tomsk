import uuid
from io import BytesIO
from xml.etree import ElementTree
from zipfile import ZipFile

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.utils import timezone
import fitz

from accounts.roles import assign_role
from forums.models import Forum, EventDay, Event
from .badge_docx import DOCX_CONTENT_TYPE, WORD_NAMESPACE
from .models import Participant, Registration, RegistrationItem, Ticket, CheckIn


@override_settings(SECURE_SSL_REDIRECT=False, ADMIN_TOTP_REQUIRED=False,
                   ALLOWED_HOSTS=['admin.localhost'], ADMIN_HOSTS={'admin.localhost'})
class CheckinDeskTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        forum = Forum.objects.create(slug='promtour', title='Форум', starts_at=now, ends_at=now+timezone.timedelta(days=1))
        person = Participant.objects.create(forum=forum, first_name='Иван', last_name='Иванов', middle_name='Иванович',
            email='test@example.org', phone='79991234567', organization='Предприятие', position='Директор', category='business')
        cls.registration = Registration.objects.create(participant=person)
        day = EventDay.objects.create(forum=forum, date=now.date())
        event = Event.objects.create(day=day, title='Вход', start_time='09:00', end_time='12:00')
        RegistrationItem.objects.create(registration=cls.registration, event=event, status='confirmed')
        cls.ticket = Ticket.objects.create(registration=cls.registration)
        cls.user = get_user_model().objects.create_user('desk', is_staff=True)
        cls.user.user_permissions.add(Permission.objects.get(codename='add_checkin'))
        cls.editor = get_user_model().objects.create_user('editor', is_staff=True)

    def test_find_by_name_phone_and_short_code(self):
        self.client.force_login(self.user)
        for q in ['Иванов Иван', '+7 (999) 123', str(self.ticket.public_id)[:8].upper(), 'test@example.org']:
            r = self.client.post('/admin/check-in/', {'search': q}, HTTP_HOST='admin.localhost')
            self.assertContains(r, str(self.ticket.public_id))

    def test_checkin_is_confirmed_once_and_does_not_change_registration(self):
        self.client.force_login(self.user)
        url = f'/admin/check-in/{self.ticket.public_id}/'
        for _ in range(2):
            self.assertEqual(self.client.post(url, {'action': 'confirm'}, HTTP_HOST='admin.localhost').status_code, 302)
        self.assertEqual(CheckIn.objects.filter(ticket=self.ticket).count(), 1)
        self.assertEqual(CheckIn.objects.get().admin_user, self.user)

    def test_revoked_and_unknown_ticket_show_an_explanation(self):
        self.client.force_login(self.user)
        self.ticket.status = Ticket.Status.REVOKED; self.ticket.save()
        r = self.client.get(f'/admin/check-in/{self.ticket.public_id}/', HTTP_HOST='admin.localhost')
        self.assertContains(r, 'Билет отменён', status_code=410)
        self.assertNotContains(r, 'Подтвердить прибытие', status_code=410)
        self.assertEqual(self.client.get(f'/admin/check-in/{uuid.uuid4()}/', HTTP_HOST='admin.localhost').status_code, 404)

    def test_staff_without_ticket_permissions_cannot_scan_or_download(self):
        self.client.force_login(self.editor)
        self.assertEqual(self.client.get('/admin/check-in/', HTTP_HOST='admin.localhost').status_code, 403)
        self.assertEqual(self.client.get(f'/api/v1/tickets/{self.ticket.public_id}/qr.png', HTTP_HOST='admin.localhost').status_code, 404)

    def test_badge_is_available_before_arrival_without_marking_checkin(self):
        self.client.force_login(self.user)
        ticket = f'/admin/check-in/{self.ticket.public_id}/'
        badge = ticket + 'badge.pdf'
        event = self.registration.items.get().event
        unrelated_event = Event.objects.create(day=event.day, title='Другой вход', start_time='13:00', end_time='14:00')
        self.assertEqual(self.client.get(badge + f'?event={unrelated_event.id}', HTTP_HOST='admin.localhost').status_code, 404)
        self.assertEqual(self.client.get(badge, HTTP_HOST='admin.localhost').status_code, 200)

        badge += f'?event={event.id}'
        response = self.client.get(badge, HTTP_HOST='admin.localhost')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertIn('no-store', response['Cache-Control'])
        with fitz.open(stream=response.content, filetype='pdf') as pdf:
            self.assertEqual(len(pdf), 1)
            page = pdf[0]
            self.assertAlmostEqual(page.rect.width / 72 * 25.4, 70, places=3)
            self.assertAlmostEqual(page.rect.height / 72 * 25.4, 50, places=3)
            rendered_lines = page.get_text().splitlines()
            self.assertEqual(rendered_lines[0], 'Предприятие')
            self.assertEqual(' '.join(rendered_lines[1:]), 'ИВАНОВ Иван')
            spans = [line['spans'][0] for block in page.get_text('dict')['blocks'] for line in block['lines']]
            self.assertNotIn('Bold', spans[0]['font'])
            for span in spans[1:]:
                self.assertIn('Bold', span['font'])
                self.assertAlmostEqual((span['bbox'][0] + span['bbox'][2]) / 2, page.rect.width / 2, places=1)
                self.assertGreater(span['size'], spans[0]['size'])

        moderator = get_user_model().objects.create_user('badge-moderator', is_staff=True)
        assign_role(moderator, 'moderator')
        self.client.force_login(moderator)
        card_url = ticket + f'?event={event.id}'
        card = self.client.get(card_url, HTTP_HOST='admin.localhost')
        self.assertContains(card, 'data-print-badge')
        self.assertContains(card, 'Пропустить участника')
        self.assertNotContains(card, 'Участник пропущен')
        self.assertContains(card, 'badge-sheet')
        self.assertContains(card, 'Скачать PDF 70 × 50 мм')
        self.assertContains(card, 'Скачать Word')
        print_view = self.client.get(badge + '&print=1', HTTP_HOST='admin.localhost')
        self.assertContains(print_view, 'workspace/badge-sheet.css')
        self.assertContains(print_view, 'ИВАНОВ')
        self.assertContains(print_view, 'Предприятие')
        self.assertNotContains(print_view, 'Иванович')
        word_url = ticket + f'badge.docx?event={event.id}'
        word = self.client.get(word_url, HTTP_HOST='admin.localhost')
        self.assertEqual(word.status_code, 200)
        self.assertEqual(word['Content-Type'], DOCX_CONTENT_TYPE)
        self.assertIn('.docx', word['Content-Disposition'])
        self.assertIn('no-store', word['Cache-Control'])
        with ZipFile(BytesIO(word.content)) as archive:
            document = ElementTree.fromstring(archive.read('word/document.xml'))
        ns = {'w': WORD_NAMESPACE}
        page_size = document.find('.//w:pgSz', ns)
        self.assertEqual(page_size.get(f'{{{WORD_NAMESPACE}}}w'), '3969')
        self.assertEqual(page_size.get(f'{{{WORD_NAMESPACE}}}h'), '2835')
        runs = document.findall('.//w:r', ns)
        self.assertEqual(runs[0].find('w:t', ns).text, 'Предприятие')
        self.assertEqual(' '.join(run.find('w:t', ns).text for run in runs[1:]), 'ИВАНОВ Иван')
        self.assertTrue(all(run.find('w:rPr/w:b', ns) is not None for run in runs[1:]))
        self.assertFalse(CheckIn.objects.exists())
        self.client.post(ticket, {'action': 'confirm', 'event': event.id}, HTTP_HOST='admin.localhost')
        card = self.client.get(card_url, HTTP_HOST='admin.localhost')
        self.assertContains(card, 'Участник пропущен')
        self.assertContains(card, 'data-print-badge')
        self.assertEqual(CheckIn.objects.count(), 1)

        self.client.force_login(self.editor)
        self.assertEqual(self.client.get(badge, HTTP_HOST='admin.localhost').status_code, 403)
        self.assertEqual(self.client.get(word_url, HTTP_HOST='admin.localhost').status_code, 403)
