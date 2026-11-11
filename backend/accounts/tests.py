from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings


@override_settings(ADMIN_OWNER_USERNAME='director', ADMIN_HOSTS=['admin.testserver'],
                   ALLOWED_HOSTS=['admin.testserver'], SECURE_SSL_REDIRECT=False)
class AccountOwnershipTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        users = get_user_model()
        cls.owner = users.objects.create_superuser('director', password='test-owner-password')
        cls.staff = users.objects.create_user('editor', password='test-staff-password', is_staff=True)
        cls.staff.user_permissions.set(Permission.objects.all())
        cls.other_superuser = users.objects.create_superuser('other', password='test-other-password')

    def login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['admin_2fa_verified'] = True
        session['admin_2fa_user_id'] = user.id
        session.save()

    def get(self, path):
        return self.client.get(path, HTTP_HOST='admin.testserver')

    def test_only_owner_can_manage_accounts_even_with_all_permissions(self):
        paths = ['/admin/auth/user/', '/admin/auth/user/add/',
                 f'/admin/auth/user/{self.owner.pk}/change/',
                 f'/admin/auth/user/{self.owner.pk}/password/',
                 '/admin/auth/group/', '/admin/auth/group/add/',
                 '/admin/accounts/admin2faprofile/']
        for user in (self.staff, self.other_superuser):
            self.login(user)
            for path in paths:
                with self.subTest(user=user.username, path=path):
                    self.assertEqual(self.get(path).status_code, 403)

    def test_owner_can_create_staff_account(self):
        self.login(self.owner)
        self.assertEqual(self.get('/admin/auth/user/add/').status_code, 200)
        response = self.client.post('/admin/auth/user/add/', {
            'username': 'new-editor', 'password1': 'New-account-pass-784!',
            'password2': 'New-account-pass-784!', 'usable_password': 'true',
            'role': 'registration',
        }, HTTP_HOST='admin.testserver')
        self.assertEqual(response.status_code, 302)
        user = get_user_model().objects.get(username='new-editor')
        self.assertTrue(user.is_staff)
        self.assertTrue(user.has_perm('registrations.change_registrationitem'))
        self.assertFalse(user.has_perm('auth.add_user'))

    def test_non_owner_cannot_create_account_by_post(self):
        self.login(self.other_superuser)
        response = self.client.post('/admin/auth/user/add/', {
            'username': 'unauthorized', 'password1': 'New-account-pass-784!',
            'password2': 'New-account-pass-784!',
        }, HTTP_HOST='admin.testserver')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(get_user_model().objects.filter(username='unauthorized').exists())

    def test_owner_cannot_be_deleted_individually_or_in_bulk(self):
        self.login(self.owner)
        self.assertEqual(self.get(f'/admin/auth/user/{self.owner.pk}/delete/').status_code, 403)
        response = self.client.post('/admin/auth/user/', {
            'action': 'delete_selected', '_selected_action': [self.owner.pk], 'post': 'yes',
        }, HTTP_HOST='admin.testserver')
        self.assertEqual(response.status_code, 403)
        self.assertTrue(get_user_model().objects.filter(pk=self.owner.pk).exists())

    def test_owner_identity_and_active_permissions_are_read_only(self):
        self.login(self.owner)
        response = self.get(f'/admin/auth/user/{self.owner.pk}/change/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'name="username"')
        self.assertNotContains(response, 'name="is_superuser"')

    @override_settings(ADMIN_TOTP_REQUIRED=False)
    def test_password_login_can_use_admin_when_totp_is_disabled(self):
        self.client.force_login(self.owner)
        self.assertEqual(self.get('/admin/').status_code, 200)
        self.assertEqual(self.get('/admin/auth/user/add/').status_code, 200)

    @override_settings(ADMIN_TOTP_REQUIRED=True)
    def test_totp_can_be_required_again(self):
        self.client.force_login(self.owner)
        response = self.get('/admin/')
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response['Location'].startswith('/admin/2fa/setup/'))

    @override_settings(ADMIN_TOTP_REQUIRED=False)
    def test_content_editor_cannot_bypass_role_using_direct_api_or_export(self):
        from .roles import assign_role
        user = get_user_model().objects.create_user('content-editor', password='test-editor', is_staff=True)
        assign_role(user, 'content')
        self.client.force_login(user)
        for path in ('/api/v1/admin/registrations/', '/admin/exports/', '/admin/check-in/'):
            with self.subTest(path=path):
                self.assertEqual(self.get(path).status_code, 403)
        self.assertEqual(self.get('/admin/forums/event/').status_code, 200)

    @override_settings(ADMIN_TOTP_REQUIRED=False)
    def test_dashboard_has_russian_task_navigation(self):
        self.client.force_login(self.owner)
        response = self.get('/admin/')
        self.assertContains(response, 'Что нужно сделать?')
        self.assertContains(response, 'Сотрудники')
        self.assertNotContains(response, '>Contests<')
        self.assertNotContains(response, '>Participants<')

    @override_settings(ADMIN_TOTP_REQUIRED=False)
    def test_moderation_button_uses_workflow_and_records_history(self):
        from datetime import time
        from django.utils import timezone
        from forums.models import Forum, EventDay, Event
        from registrations.models import Participant, Registration, RegistrationItem, NotificationOutbox
        now = timezone.now()
        forum = Forum.objects.create(slug='moderation', title='Форум', series='promtour', starts_at=now,
                                     ends_at=now + timezone.timedelta(days=1), status='published')
        day = EventDay.objects.create(forum=forum, date=now.date(), title='Программа')
        event = Event.objects.create(day=day, title='Маршрут', kind='route', registration_policy='moderated',
                                     start_time=time(10), end_time=time(11), slug='route', is_published=True)
        person = Participant.objects.create(forum=forum, first_name='Тест', last_name='Участник',
                                            email='test@example.org', phone='79991234567', category='business')
        registration = Registration.objects.create(participant=person, email_verified_at=now)
        item = RegistrationItem.objects.create(registration=registration, event=event, status='pending_review')
        self.client.force_login(self.owner)
        response = self.client.post(f'/admin/registrations/registrationitem/{item.pk}/change/',
                                    {'_moderation_action': 'approve', 'decision_note': 'Проверено'},
                                    HTTP_HOST='admin.testserver')
        self.assertEqual(response.status_code, 302)
        item.refresh_from_db()
        self.assertEqual(item.status, 'approved')
        self.assertEqual(item.decided_by, self.owner)
        self.assertTrue(item.history.filter(actor_user=self.owner, action='approve').exists())
        self.assertTrue(NotificationOutbox.objects.filter(kind='moderation_decision').exists())
