from datetime import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings
from django.utils import timezone

from forums.models import Event, EventDay, Forum
from .models import NotificationOutbox, Participant, Registration, RegistrationItem
from .notifications import message_content, process_one
from .selection import RegistrationError
from .workflow import decide_item, decision_personal_url, registration_by_token, token_hash


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', PUBLIC_SITE_URL='https://forum.example',
                   SECURE_SSL_REDIRECT=False, ADMIN_TOTP_REQUIRED=False, ALLOWED_HOSTS=['admin.localhost'], ADMIN_HOSTS={'admin.localhost'})
class ModerationMailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.forum = Forum.objects.create(slug='test', title='Форум', starts_at=now, ends_at=now+timezone.timedelta(days=2))
        day = EventDay.objects.create(forum=cls.forum, date=now.date())
        cls.route = Event.objects.create(day=day, title='Маршрут 1', kind='route', registration_policy='moderated', start_time=time(9,15), end_time=time(12), is_published=True)
        person = Participant.objects.create(forum=cls.forum, first_name='Иван', last_name='Тестовый', email='test@example.org', phone='79990000000', organization='Тест', position='Участник', category='business')
        cls.registration = Registration.objects.create(participant=person, email_verified_at=now, token_issued_at=now, access_token_hash=token_hash('original-access'))
        cls.item = RegistrationItem.objects.create(registration=cls.registration, event=cls.route, status='pending_review')
        cls.admin = get_user_model().objects.create_superuser('director', 'director@example.org', 'test-only')

    def token(self, url):
        return parse_qs(urlsplit(url).query)['t'][0]

    def test_approval_sends_a_separate_confirmation_and_keeps_existing_access(self):
        previous = NotificationOutbox.objects.create(registration=self.registration, recipient='test@example.org', kind='registration_summary', payload={}, dedup_key='previous', status='sent')
        decide_item(self.item.pk, 'approve', self.admin)
        notification = NotificationOutbox.objects.get(kind='moderation_decision')
        subject, body = message_content(notification)
        self.assertIn('заявка подтверждена', subject)
        self.assertIn('Маршрут 1', body)
        token = self.token(notification.payload['personal_url'])
        self.assertLessEqual(len(token), 200)
        self.assertEqual(registration_by_token(token).pk, self.registration.pk)
        self.assertEqual(registration_by_token('original-access').pk, self.registration.pk)
        with patch('registrations.notifications.ticket_email_attachments', return_value=[]):
            self.assertEqual(process_one(), 'sent')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Ваша заявка подтверждена.', mail.outbox[0].body)
        notification.refresh_from_db(); self.assertNotIn('personal_url', notification.payload)
        previous.refresh_from_db(); self.assertEqual(previous.status, 'sent')
        with self.assertRaises(RegistrationError):
            decide_item(self.item.pk, 'approve', self.admin)
        self.assertEqual(NotificationOutbox.objects.filter(kind='moderation_decision').count(), 1)

    def test_rejection_explains_no_places_and_links_to_the_existing_registration(self):
        decide_item(self.item.pk, 'reject', self.admin)
        notification = NotificationOutbox.objects.get(kind='moderation_decision')
        _, body = message_content(notification)
        self.assertIn('нет свободных мест', body)
        self.assertIn('забронируйте другой маршрут', body)
        self.assertIn('Изменить мероприятия', body)
        self.assertIn(notification.payload['personal_url'], body)
        self.assertEqual(registration_by_token(self.token(notification.payload['personal_url'])).pk, self.registration.pk)

    def test_admin_cancellation_notifies_and_preserves_the_actual_reason(self):
        decide_item(self.item.pk, 'approve', self.admin)
        decide_item(self.item.pk, 'cancel', self.admin, note='Отмена по просьбе участника')
        notification = NotificationOutbox.objects.filter(kind='moderation_decision').latest('created_at')
        _, body = message_content(notification)
        self.assertIn('Отмена по просьбе участника', body)
        self.assertNotIn('нет свободных мест', body)
        self.assertIn(notification.payload['personal_url'], body)

    def test_signed_links_reject_tampering_expire_and_follow_access_rotation(self):
        token = self.token(decision_personal_url(self.registration))
        self.assertIsNone(registration_by_token(token + 'x'))
        with patch('django.core.signing.time.time', return_value=timezone.now().timestamp()+31*86400):
            self.assertIsNone(registration_by_token(token))
        self.registration.access_token_hash = token_hash('new-access'); self.registration.save()
        self.assertIsNone(registration_by_token(token))
        self.assertEqual(registration_by_token('new-access').pk, self.registration.pk)
        for invalid in ['!', 'не токен', 'x'*201]:
            self.assertIsNone(registration_by_token(invalid))

    def test_parent_registration_links_to_the_actual_moderation_buttons(self):
        self.client.force_login(self.admin)
        response = self.client.get(f'/admin/registrations/registration/{self.registration.pk}/change/', HTTP_HOST='admin.localhost')
        self.assertContains(response, 'Одобрить или отклонить маршрут')
        self.assertContains(response, f'/admin/registrations/registrationitem/{self.item.pk}/change/#moderation-decision')
        self.item.refresh_from_db(); self.assertEqual(self.item.status, 'pending_review')
