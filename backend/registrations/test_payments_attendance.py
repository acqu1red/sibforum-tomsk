from datetime import time
from hashlib import sha256
from io import BytesIO
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.db import DatabaseError, connection, transaction
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image
from openpyxl import load_workbook

from accounts.roles import assign_role
from forums.models import Forum, EventDay, Event
from .models import Participant, Registration, RegistrationItem, PaymentInstruction, PaymentConfirmation, NotificationOutbox, Ticket, CheckIn
from .workflow import decide_item, registration_payload
from .tickets import ensure_ticket, build_ticket_pdf
from .notifications import process_one
from .selection import RegistrationError


@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend', SECURE_SSL_REDIRECT=False,
                   ADMIN_TOTP_REQUIRED=False, ALLOWED_HOSTS=['admin.localhost'], ADMIN_HOSTS={'admin.localhost'})
class PaymentsAttendanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.forum = Forum.objects.create(slug='promtour', title='Тест', starts_at=now, ends_at=now+timezone.timedelta(days=2))
        day = EventDay.objects.create(forum=cls.forum, date=now.date())
        cls.paid = Event.objects.create(day=day, title='Платная экскурсия', kind='route', registration_policy='moderated', is_paid=True, price='2500.00', payment_note='Оплата по QR после одобрения', start_time=time(10), end_time=time(12))
        cls.free = Event.objects.create(day=day, title='Бесплатная встреча', start_time=time(13), end_time=time(15))
        person = Participant.objects.create(forum=cls.forum, first_name='Тест', last_name='Участник', organization='=FORMULA()', email='test@example.invalid', phone='79999990000')
        cls.registration = Registration.objects.create(participant=person, email_verified_at=now)
        cls.item = RegistrationItem.objects.create(registration=cls.registration, event=cls.paid, status='pending_review')
        png = BytesIO(); Image.new('RGB', (20, 20), 'white').save(png, format='PNG')
        cls.asset = PaymentInstruction.objects.create(forum=cls.forum, source_filename='test.pdf', pdf_bytes=b'%PDF-test-only', qr_png=png.getvalue(), pdf_sha256=sha256(b'%PDF-test-only').hexdigest())
        cls.gate = get_user_model().objects.create_user('gate', is_staff=True); assign_role(cls.gate, 'checkin')
        cls.moderator = get_user_model().objects.create_user('moderator', is_staff=True); assign_role(cls.moderator, 'moderator')
        cls.owner = get_user_model().objects.create_superuser('director', password='test-only')

    def get(self, path):
        return self.client.get(path, HTTP_HOST='admin.localhost')

    def post(self, path, data):
        return self.client.post(path, data, HTTP_HOST='admin.localhost')

    def approve(self):
        return decide_item(self.item.id, 'approve', self.moderator)

    def test_paid_approval_only_requests_payment_with_original_assets_no_ticket(self):
        item = self.approve()
        self.assertEqual(item.payment_status, 'awaiting')
        self.assertEqual(item.payment_amount, 2500)
        self.assertFalse(Ticket.objects.exists())
        self.assertEqual(list(NotificationOutbox.objects.values_list('kind', flat=True)), ['payment_request'])
        with patch('registrations.notifications.ticket_email_attachments', side_effect=AssertionError('No admission at approval')):
            self.assertEqual(process_one(), 'sent')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('ndv@tomsktpp.ru', mail.outbox[0].body)
        self.assertEqual([a.filename for a in mail.outbox[0].attachments], ['payment-qr.pdf', 'payment-qr.png'])
        self.assertEqual(mail.outbox[0].attachments[0].content, bytes(self.asset.pdf_bytes))
        with self.assertRaises(RegistrationError): self.approve()
        self.assertEqual(NotificationOutbox.objects.count(), 1)

    def test_receipt_confirmation_issues_ticket_and_is_single(self):
        item = self.approve(); process_one()
        with self.assertRaises(RegistrationError): decide_item(item.id, 'confirm_payment', self.gate)
        decide_item(item.id, 'confirm_payment', self.moderator, note='Квитанция проверена')
        self.assertEqual(PaymentConfirmation.objects.get().actor, self.moderator)
        self.assertEqual(Ticket.objects.get().status, 'active')
        self.assertEqual(process_one(), 'sent')
        self.assertEqual(len(mail.outbox), 2)
        self.assertIn('входной билет', mail.outbox[1].subject)
        self.assertTrue(any(a.filename.endswith('.pdf') for a in mail.outbox[1].attachments))
        self.assertFalse(any(a.filename == 'payment-qr.pdf' for a in mail.outbox[1].attachments))
        with self.assertRaises(RegistrationError): decide_item(item.id, 'confirm_payment', self.moderator)
        self.assertEqual(PaymentConfirmation.objects.count(), 1)

    def test_stale_payment_mail_is_cancelled_after_cancel_or_confirmation(self):
        item = self.approve()
        decide_item(item.id, 'confirm_payment', self.moderator)
        self.assertEqual(process_one(), 'cancelled')
        self.assertEqual(process_one(), 'sent')
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn('Оплата подтверждена', mail.outbox[0].subject)

    def test_cancelled_payment_confirmation_email_is_not_sent(self):
        item = self.approve(); process_one()
        decide_item(item.id, 'confirm_payment', self.moderator)
        decide_item(item.id, 'cancel', self.moderator)
        self.assertEqual(process_one(), 'cancelled')
        self.assertEqual(len(mail.outbox), 1)

    def test_previous_approvals_prepare_without_email_and_two_manual_buttons(self):
        self.item.status = 'approved'; self.item.save()
        call_command('prepare_existing_payments', forum='promtour', expected=1, stdout=__import__('io').StringIO())
        self.item.refresh_from_db(); self.assertEqual(self.item.payment_status, 'awaiting')
        self.assertFalse(NotificationOutbox.objects.exists())
        self.client.force_login(self.moderator)
        response = self.get(f'/admin/registrations/registrationitem/{self.item.id}/change/')
        self.assertContains(response, 'Отправить письмо с QR для оплаты')
        self.assertContains(response, 'Квитанция проверена — подтвердить оплату')
        for _ in range(2):
            self.post(f'/admin/registrations/registrationitem/{self.item.id}/change/', {'_moderation_action': 'send_payment_request'})
        self.assertEqual(NotificationOutbox.objects.filter(kind='payment_request').count(), 1)
        self.assertFalse(PaymentConfirmation.objects.exists())

    def test_previous_paid_can_be_confirmed_without_requesting_payment_again(self):
        self.item.status = 'approved'; self.item.save()
        call_command('prepare_existing_payments', forum='promtour', expected=1, stdout=__import__('io').StringIO())
        decide_item(self.item.id, 'confirm_payment', self.moderator)
        self.assertEqual(list(NotificationOutbox.objects.values_list('kind', flat=True)), ['payment_confirmed'])

    def test_missing_asset_rolls_back_approval(self):
        with patch('registrations.payments.PaymentInstruction.objects.filter') as query:
            query.return_value.first.return_value = None
            with self.assertRaises(RegistrationError): self.approve()
        self.item.refresh_from_db(); self.assertEqual(self.item.status, 'pending_review')
        self.assertFalse(NotificationOutbox.objects.exists())

    def test_scan_get_does_not_check_in_unpaid_is_blocked_event_scope_enforced(self):
        RegistrationItem.objects.create(registration=self.registration, event=self.free, status='confirmed')
        ticket = ensure_ticket(self.registration)
        self.approve()
        self.client.force_login(self.gate)
        url = f'/admin/check-in/{ticket.public_id}/'
        self.assertContains(self.get(url), 'Пропустить участника')
        self.assertEqual(CheckIn.objects.count(), 0)
        self.post(url, {'action': 'confirm', 'event': str(self.paid.id)})
        self.assertEqual(CheckIn.objects.count(), 0)
        decide_item(self.item.id, 'confirm_payment', self.moderator)
        for _ in range(2): self.post(url, {'action': 'confirm', 'event': str(self.paid.id)})
        self.assertEqual(CheckIn.objects.count(), 1)
        self.assertEqual(CheckIn.objects.get().event, self.paid)
        self.assertIsNone(registration_payload(self.registration)['ticket']['checked_in_at'])
        self.post(url, {'action': 'confirm'})
        self.assertEqual(CheckIn.objects.count(), 2)

    def test_mixed_ticket_pdf_lists_only_admitted_events(self):
        import fitz
        RegistrationItem.objects.create(registration=self.registration, event=self.free, status='confirmed')
        ensure_ticket(self.registration); self.approve()
        doc = fitz.open(stream=build_ticket_pdf(self.registration), filetype='pdf')
        text = ''.join(p.get_text() for p in doc)
        self.assertIn(self.free.title, text)
        self.assertNotIn(self.paid.title, text)

    def test_restricted_gate_permissions_and_fresh_excel(self):
        self.client.force_login(self.gate)
        self.assertRedirects(self.get('/admin/'), '/admin/check-in/', fetch_redirect_response=False)
        for url in ['/admin/auth/user/', '/admin/forums/event/', '/admin/registrations/registration/', '/admin/exports/', '/api/v1/admin/registrations/']:
            self.assertEqual(self.get(url).status_code, 403, url)
        self.assertEqual(self.post(f'/api/v1/admin/registration-items/{self.item.id}/decision/', {'action':'approve'}).status_code in (403,404), True)
        RegistrationItem.objects.create(registration=self.registration, event=self.free, status='confirmed')
        ticket = ensure_ticket(self.registration)
        before = self.get('/admin/attendance/?format=xlsx')
        self.assertEqual(load_workbook(BytesIO(before.content)).worksheets[0].max_row, 1)
        self.post(f'/admin/check-in/{ticket.public_id}/', {'action': 'confirm'})
        after = self.get('/admin/attendance/?format=xlsx')
        ws = load_workbook(BytesIO(after.content)).worksheets[0]
        self.assertEqual(ws.max_row, 2)
        self.assertTrue(ws.cell(2,3).value.startswith("'="))
        self.assertIn('no-store', after['Cache-Control'])
        self.assertEqual(self.get('/admin/attendance/?format=json').json()['summary']['marks'], 1)
        self.assertEqual(self.get(f'/api/v1/tickets/{ticket.public_id}/ticket.pdf').status_code, 404)

    def test_payment_evidence_is_immutable_in_postgres(self):
        if connection.vendor != 'postgresql': self.skipTest('PostgreSQL trigger')
        with self.assertRaises(DatabaseError), transaction.atomic():
            PaymentInstruction.objects.filter(id=self.asset.id).update(source_filename='changed')
        self.approve(); decide_item(self.item.id, 'confirm_payment', self.moderator)
        with self.assertRaises(DatabaseError), transaction.atomic():
            PaymentConfirmation.objects.all().update(amount='1.00')


from concurrent.futures import ThreadPoolExecutor
from unittest import skipUnless
from django.db import close_old_connections, connections
from django.test import TransactionTestCase, Client


@skipUnless(connection.vendor == 'postgresql', 'Requires PostgreSQL row locks')
@override_settings(SECURE_SSL_REDIRECT=False, ADMIN_TOTP_REQUIRED=False,
                   ALLOWED_HOSTS=['admin.localhost'], ADMIN_HOSTS={'admin.localhost'})
class PaymentArrivalConcurrencyTests(TransactionTestCase):
    def setUp(self):
        now = timezone.now()
        f = Forum.objects.create(slug='promtour', title='QA', starts_at=now, ends_at=now+timezone.timedelta(days=1))
        d = EventDay.objects.create(forum=f, date=now.date())
        e = Event.objects.create(day=d, title='QA route', start_time=time(10), end_time=time(12), kind='route', registration_policy='moderated', is_paid=True, price='2500.00', payment_note='QR')
        p = Participant.objects.create(forum=f, first_name='QA', last_name='QA', email='qa@example.invalid')
        self.registration = Registration.objects.create(participant=p)
        self.item = RegistrationItem.objects.create(registration=self.registration, event=e, status='pending_review')
        PaymentInstruction.objects.create(forum=f, source_filename='test.pdf', pdf_bytes=b'%PDF-test', qr_png=b'test', pdf_sha256='a'*64)
        self.owner = get_user_model().objects.create_superuser('director', password='qa-only')
        decide_item(self.item.id, 'approve', self.owner)

    def test_parallel_receipt_confirmations_create_one_record_one_ticket_one_mail(self):
        def confirm(index):
            close_old_connections()
            try:
                decide_item(self.item.id, 'confirm_payment', get_user_model().objects.get(pk=self.owner.pk))
                return 'confirmed'
            except RegistrationError as error:
                return error.code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(confirm, range(6)))
        self.assertEqual(results.count('confirmed'), 1)
        self.assertEqual(results.count('invalid_transition'), 5)
        self.assertEqual(PaymentConfirmation.objects.count(), 1)
        self.assertEqual(Ticket.objects.count(), 1)
        self.assertEqual(NotificationOutbox.objects.filter(kind='payment_confirmed').count(), 1)

    def test_parallel_arrivals_create_one_mark(self):
        decide_item(self.item.id, 'confirm_payment', self.owner)
        ticket = Ticket.objects.get()
        gate = get_user_model().objects.create_user('gate', is_staff=True); assign_role(gate, 'checkin')
        def admit(index):
            close_old_connections()
            try:
                client = Client(); client.force_login(get_user_model().objects.get(pk=gate.pk))
                return client.post(f'/admin/check-in/{ticket.public_id}/', {'action':'confirm','event':str(self.item.event_id)}, HTTP_HOST='admin.localhost').status_code
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(admit, range(6)))
        self.assertEqual(results, [302]*6)
        self.assertEqual(CheckIn.objects.count(), 1)
