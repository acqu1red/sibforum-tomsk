import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.utils import timezone

from forums.models import Forum
from .models import Participant, Registration, Ticket, CheckIn


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
