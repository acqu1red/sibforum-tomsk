from datetime import time
from urllib.parse import parse_qs, urlsplit
import uuid

from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import check_password
from django.contrib.auth.models import Permission
from django.contrib.admin.models import LogEntry
from django.core import mail
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from forums.models import Event, EventDay, Forum
from .assistance import resend_email
from .models import EmailChallenge, NotificationOutbox, Participant, Registration, RegistrationItem, Ticket
from .notifications import process_one
from .selection import RegistrationError
from .workflow import registration_by_token, token_hash


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', PUBLIC_SITE_URL='https://forum.example',
    SECURE_SSL_REDIRECT=False, ADMIN_TOTP_REQUIRED=False, ALLOWED_HOSTS=['admin.localhost','testserver'], ADMIN_HOSTS=['admin.localhost'])
class ParticipantAssistanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now=timezone.now()
        cls.forum=Forum.objects.create(slug='promtour',title='Форум',starts_at=now,ends_at=now+timezone.timedelta(days=2))
        day=EventDay.objects.create(forum=cls.forum,date=now.date(),title='День форума')
        cls.event=Event.objects.create(day=day,title='Семинар',kind='seminar',start_time=time(10),end_time=time(12),is_published=True)
        cls.person=Participant.objects.create(forum=cls.forum,last_name='Иванов',first_name='Иван',email='fixture@example.org',phone='79990000000',organization='Компания',position='Участник',category='business')
        cls.registration=Registration.objects.create(participant=cls.person,email_verified_at=now,access_token_hash=token_hash('old-working-link'))
        cls.item=RegistrationItem.objects.create(registration=cls.registration,event=cls.event,status='confirmed')
        cls.ticket=Ticket.objects.create(registration=cls.registration)
        cls.staff=get_user_model().objects.create_superuser('director', 'staff@example.org', 'unit-test-only')

    def setUp(self):
        self.client.force_login(self.staff)

    def post(self,key=None,client=None):
        return (client or self.client).post(reverse('registration-resend',args=[self.registration.pk]),
            {'request_key':str(key or uuid.uuid4())}, HTTP_HOST='admin.localhost',HTTP_ACCEPT='application/json')

    def test_verified_resend_keeps_registration_access_and_sends_actual_ticket(self):
        old_id=self.ticket.public_id
        response=self.post()
        self.assertEqual(response.status_code,200,response.content)
        notification=NotificationOutbox.objects.get()
        self.assertEqual(notification.kind,'registration_summary')
        self.assertEqual(notification.recipient,self.person.email)
        token=parse_qs(urlsplit(notification.payload['personal_url']).query)['t'][0]
        self.assertEqual(registration_by_token(token).pk,self.registration.pk)
        self.assertEqual(registration_by_token('old-working-link').pk,self.registration.pk)
        self.assertEqual(process_one(),'sent')
        self.assertEqual(len(mail.outbox),1)
        self.assertEqual(len(mail.outbox[0].attachments),2)
        self.assertTrue(mail.outbox[0].attachments[0][1].startswith(b'%PDF'))
        self.assertTrue(mail.outbox[0].attachments[1][1].startswith(b'\x89PNG'))
        self.assertEqual((Participant.objects.count(),Registration.objects.count(),RegistrationItem.objects.count(),Ticket.objects.count()),(1,1,1,1))
        self.ticket.refresh_from_db();self.registration.refresh_from_db()
        self.assertEqual(self.ticket.public_id,old_id)
        self.assertEqual(self.registration.version,1)
        self.assertEqual(LogEntry.objects.filter(user=self.staff,object_id=str(self.registration.pk)).count(),1)

    def test_pending_resend_refreshes_code_without_recreating_selection_or_person(self):
        self.registration.email_verified_at=None;self.registration.access_token_hash='';self.registration.save()
        self.ticket.delete();self.item.delete()
        person={'email':self.person.email,'last_name':'Иванов','first_name':'Иван'}
        selection=[{'event_id':str(self.event.pk)}]
        challenge=EmailChallenge(registration=self.registration,pending_person=person,pending_selection=selection,expires_at=timezone.now()-timezone.timedelta(minutes=1),attempts=5)
        challenge.set_code('111111');challenge.save()
        old=NotificationOutbox.objects.create(registration=self.registration,kind='email_verification',recipient=self.person.email,dedup_key='old-code',payload={'code':'111111'})
        self.assertEqual(self.post().status_code,200)
        old.refresh_from_db();self.assertEqual(old.status,'cancelled')
        notification=NotificationOutbox.objects.exclude(pk=old.pk).get()
        self.assertEqual(notification.kind,'email_verification')
        challenge.refresh_from_db()
        self.assertTrue(check_password(notification.payload['code'],challenge.code_hash))
        self.assertFalse(check_password('111111',challenge.code_hash))
        self.assertEqual(challenge.attempts,0)
        self.assertGreater(challenge.expires_at,timezone.now())
        self.assertEqual((challenge.pending_person,challenge.pending_selection),(person,selection))
        self.assertEqual((EmailChallenge.objects.count(),Participant.objects.count(),Registration.objects.count(),RegistrationItem.objects.count(),Ticket.objects.count()),(1,1,1,0,0))
        self.registration.refresh_from_db();self.assertFalse(self.registration.email_verified)

    def test_duplicate_request_is_idempotent_and_new_request_has_cooldown(self):
        key=uuid.uuid4()
        self.assertEqual(self.post(key).status_code,200)
        self.assertEqual(self.post(key).status_code,200)
        self.assertEqual(self.post().status_code,429)
        self.assertEqual(NotificationOutbox.objects.count(),1)
        self.assertEqual(LogEntry.objects.count(),1)
        NotificationOutbox.objects.update(created_at=timezone.now()-timezone.timedelta(seconds=61))
        self.assertEqual(self.post().status_code,200)
        self.assertEqual(NotificationOutbox.objects.count(),2)

    def test_resend_is_post_only_and_requires_csrf_and_change_permission(self):
        url=reverse('registration-resend',args=[self.registration.pk])
        self.assertEqual(self.client.get(url,HTTP_HOST='admin.localhost').status_code,405)
        strict=Client(enforce_csrf_checks=True);strict.force_login(self.staff)
        self.assertEqual(self.post(client=strict).status_code,403)
        viewer=get_user_model().objects.create_user('viewer',is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_registration'))
        self.client.force_login(viewer)
        self.assertEqual(self.post().status_code,403)
        page=self.client.get(reverse('registration-assistance',args=[self.registration.pk]),HTTP_HOST='admin.localhost')
        self.assertEqual(page.status_code,200)
        self.assertNotContains(page,'Отправить письмо ещё раз')
        self.assertNotContains(page,'data-share-ticket')
        self.assertEqual(NotificationOutbox.objects.count(),0)

    def test_staff_downloads_active_ticket_and_revoked_ticket_is_inaccessible(self):
        qr=reverse('registration-staff-qr',args=[self.registration.pk])
        pdf=reverse('registration-staff-pdf',args=[self.registration.pk])
        for url,content_type,magic in [(qr,'image/png',b'\x89PNG'),(pdf,'application/pdf',b'%PDF')]:
            response=self.client.get(url,HTTP_HOST='admin.localhost')
            self.assertEqual(response.status_code,200)
            self.assertEqual(response['Content-Type'],content_type)
            self.assertTrue(response.content.startswith(magic))
            self.assertIn('no-store',response['Cache-Control'])
            anonymous=Client().get(url,HTTP_HOST='admin.localhost')
            self.assertEqual(anonymous.status_code,302)
        self.ticket.status='revoked';self.ticket.save()
        self.assertEqual(self.client.get(qr,HTTP_HOST='admin.localhost').status_code,404)
        self.assertEqual(self.client.get(pdf,HTTP_HOST='admin.localhost').status_code,404)

    def test_download_permission_does_not_grant_resend_permission(self):
        viewer=get_user_model().objects.create_user('tickets-only',is_staff=True)
        viewer.user_permissions.add(Permission.objects.get(codename='view_registration'),Permission.objects.get(codename='view_ticket'))
        self.client.force_login(viewer)
        self.assertEqual(self.client.get(reverse('registration-staff-qr',args=[self.registration.pk]),HTTP_HOST='admin.localhost').status_code,200)
        self.assertEqual(self.post().status_code,403)

    def test_missing_pending_request_returns_help_instead_of_creating_registration(self):
        self.registration.email_verified_at=None;self.registration.save()
        response=self.post()
        self.assertEqual(response.status_code,409)
        self.assertEqual(NotificationOutbox.objects.count(),0)
        self.assertEqual(EmailChallenge.objects.count(),0)
        self.assertEqual(Registration.objects.count(),1)

    def test_buttons_are_next_to_participant_and_registration_and_detail_has_link(self):
        for model,pk in [('participant',self.person.pk),('registration',self.registration.pk)]:
            response=self.client.get(reverse(f'admin:registrations_{model}_changelist'),HTTP_HOST='admin.localhost')
            self.assertContains(response,'data-registration-resend=')
            self.assertContains(response,'QR / билет')
            response=self.client.get(reverse(f'admin:registrations_{model}_change',args=[pk]),HTTP_HOST='admin.localhost')
            self.assertContains(response,'Открыть письмо и билет участника')
        page=self.client.get(reverse('registration-assistance',args=[self.registration.pk]),HTTP_HOST='admin.localhost')
        self.assertContains(page,'data-share-ticket')
        self.assertEqual(NotificationOutbox.objects.count(),0)
