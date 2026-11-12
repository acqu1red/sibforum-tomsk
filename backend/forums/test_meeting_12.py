from datetime import time
from django.contrib.auth import get_user_model
from django.contrib.admin.models import LogEntry, DELETION
from django.core.management import call_command
from django.test import TestCase, Client, override_settings
from django.utils import timezone

from .models import Event, EventDay, Forum, ForumPage, InterfaceText, OrganizationLogo, PageSection, RouteEnterprise, Speaker


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver', 'admin.localhost'], ADMIN_HOSTS=['admin.localhost'], ADMIN_TOTP_REQUIRED=False)
class Meeting12Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.forum = Forum.objects.create(slug='promtour', title='Форум', status='published', starts_at=now, ends_at=now+timezone.timedelta(days=2))
        cls.page = ForumPage.objects.create(forum=cls.forum, brand_name='Сохранено организатором')
        cls.day = EventDay.objects.create(forum=cls.forum, date=now.date(), position=0)
        cls.route = Event.objects.create(day=cls.day, kind='route', title='Маршрут', start_time=time(9), end_time=time(12), registration_policy='moderated', is_published=True, contact_name='Куратор', contact_phone='+7 (999) 123-45-67', curator_email='private@example.org')
        cls.enterprise = RouteEnterprise.objects.create(event=cls.route, name='«Микран»')
        cls.director = get_user_model().objects.create_user('director', is_staff=True, is_superuser=True)

    def test_blank_interface_text_is_preserved_in_public_api_and_reinitialization(self):
        InterfaceText.objects.create(forum=self.forum, key='route_note', value='')
        call_command('prepare_meeting_12', verbosity=0)
        self.assertEqual(self.client.get('/api/v1/forums/promtour/program/').json()['page']['interface_texts']['route_note'], '')
        self.assertEqual(InterfaceText.objects.filter(forum=self.forum, key='route_note').count(), 1)

    def test_public_route_contact_does_not_reveal_private_curator_email(self):
        response = self.client.get('/api/v1/forums/promtour/program/')
        event = response.json()['days'][0]['events'][0]
        self.assertEqual(event['contact_name'], 'Куратор')
        self.assertEqual(event['contact_phone'], '+7 (999) 123-45-67')
        self.assertNotIn('private@example.org', response.content.decode())

    def test_preparation_changes_only_agreed_groups_and_never_overwrites_again(self):
        speaker = Speaker.objects.create(forum=self.forum, full_name='Исправлено редактором', short_position='Полная сохранённая должность', position=17)
        section = PageSection.objects.create(forum=self.forum, key='hero', heading='Авторский заголовок')
        existing = OrganizationLogo.objects.create(forum=self.forum, group='enterprises', name='Микран', static_image='/img/edited-logo.png')
        old = OrganizationLogo.objects.create(forum=self.forum, group='enterprises', name='Предприятие прошлого форума')
        call_command('prepare_meeting_12', apply_organizations=True, verbosity=0)
        existing.refresh_from_db(); old.refresh_from_db()
        self.assertEqual(existing.route_enterprise_id, self.enterprise.pk)
        self.assertEqual(existing.static_image, '/img/edited-logo.png')
        self.assertFalse(old.is_published)
        self.assertEqual(list(self.forum.organization_logos.filter(group='organizers', is_published=True).values_list('name', flat=True)), ['Торгово-промышленная палата Российской Федерации', 'Союз «Торгово-промышленная палата Томской области»', 'Администрация Томской области', 'Томский политехнический университет'])
        existing.name = 'Новое название после выпуска'; existing.position = 29; existing.is_published = False; existing.save()
        call_command('prepare_meeting_12', apply_organizations=True, verbosity=0)
        existing.refresh_from_db(); speaker.refresh_from_db(); section.refresh_from_db(); self.page.refresh_from_db()
        self.assertEqual((existing.name, existing.position, existing.is_published), ('Новое название после выпуска', 29, False))
        self.assertEqual((speaker.full_name, speaker.short_position, speaker.position), ('Исправлено редактором', 'Полная сохранённая должность', 17))
        self.assertEqual(section.heading, 'Авторский заголовок')
        self.assertEqual(self.page.brand_name, 'Сохранено организатором')

    def test_only_published_route_enterprises_appear_in_public_group(self):
        OrganizationLogo.objects.create(forum=self.forum, group='enterprises', name='Микран', route_enterprise=self.enterprise)
        OrganizationLogo.objects.create(forum=self.forum, group='enterprises', name='Старый логотип без маршрута')
        self.assertEqual(len(self.client.get('/api/v1/forums/promtour/program/').json()['page']['logos']), 1)
        self.route.is_published = False; self.route.save()
        self.assertEqual(self.client.get('/api/v1/forums/promtour/program/').json()['page']['logos'], [])

    def test_editor_creates_logo_and_deletes_it_with_audit_and_confirmation(self):
        self.client.force_login(self.director)
        response = self.client.post('/admin/site-editor/object/logo/new/', {'group':'partners', 'name':'Новый партнёр', 'image_background':'light', 'position':0, 'is_published':'on'}, HTTP_HOST='admin.localhost')
        self.assertEqual(response.status_code, 200, response.content)
        logo = OrganizationLogo.objects.get(name='Новый партнёр')
        url = f'/admin/site-editor/object/logo/{logo.pk}/delete/'
        self.assertEqual(self.client.post(url, {'_version':logo.updated_at.isoformat()}, HTTP_HOST='admin.localhost').status_code, 400)
        self.assertEqual(self.client.post(url, {'_version':'old', 'confirm':'delete'}, HTTP_HOST='admin.localhost').status_code, 409)
        self.assertEqual(self.client.post(url, {'_version':logo.updated_at.isoformat(), 'confirm':'delete'}, HTTP_HOST='admin.localhost').status_code, 200)
        self.assertFalse(OrganizationLogo.objects.filter(pk=logo.pk).exists())
        self.assertTrue(LogEntry.objects.filter(action_flag=DELETION, user=self.director).exists())

    def test_delete_requires_permission_csrf_and_current_forum(self):
        logo = OrganizationLogo.objects.create(forum=self.forum, group='partners', name='Партнёр')
        url = f'/admin/site-editor/object/logo/{logo.pk}/delete/'
        client = Client(enforce_csrf_checks=True); client.force_login(self.director)
        self.assertEqual(client.post(url, {'confirm':'delete'}, HTTP_HOST='admin.localhost').status_code, 403)
        viewer = get_user_model().objects.create_user('viewer', is_staff=True)
        self.client.force_login(viewer)
        self.assertEqual(self.client.post(url, {'confirm':'delete'}, HTTP_HOST='admin.localhost').status_code, 403)
        self.assertTrue(OrganizationLogo.objects.filter(pk=logo.pk).exists())

    @override_settings(DEBUG=True)
    def test_plenary_registration_without_route_then_add_route_after_email(self):
        from registrations.workflow import submit_registration, verify_email
        day = EventDay.objects.create(forum=self.forum, date=self.day.date+timezone.timedelta(days=1), position=1)
        plenary = Event.objects.create(day=day, kind='plenary', title='Открытие', start_time=time(10), end_time=time(11), registration_policy='auto', is_published=True)
        person = dict(last_name='Иванов', first_name='Иван', middle_name='Иванович', email='test@example.org', phone='+79991234567', organization='Компания', position='Директор', category='business')
        consents = {'pd':True,'policy':True}
        result = submit_registration(self.forum, person, [{'event_id':str(plenary.pk)}], consents)
        registration, old_token = verify_email(self.forum, person['email'], result['debug_code'])
        self.assertEqual(registration.items.get().status, 'confirmed')
        result = submit_registration(self.forum, person, [{'event_id':str(plenary.pk)}, {'event_id':str(self.route.pk)}], consents)
        self.assertEqual(registration.items.count(), 1)
        updated, new_token = verify_email(self.forum, person['email'], result['debug_code'])
        self.assertNotEqual(old_token, new_token)
        self.assertEqual(updated.items.get(event=plenary).status, 'confirmed')
        self.assertEqual(updated.items.get(event=self.route).status, 'pending_review')

    def test_route_contacts_can_be_saved_replaced_and_cleared_in_editor(self):
        self.client.force_login(self.director)
        url = f'/admin/site-editor/object/event/{self.route.pk}/'
        form = self.client.get(url, HTTP_HOST='admin.localhost').json()['html']
        self.assertIn('Контакт маршрута', form)
        from .editor import SPECS
        from django.forms.models import model_to_dict
        for name, phone in [('Анна Петрова', '+7 (999) 111-22-33'), ('Иван Сидоров', '+7 (999) 444-55-66'), ('', '')]:
            self.route.refresh_from_db()
            data = {k: v for k, v in model_to_dict(self.route, fields=SPECS['event'][3]).items() if v is not None and v is not False}
            data.update(_version=self.route.updated_at.isoformat(), contact_name=name, contact_phone=phone)
            data.update({'talks-TOTAL_FORMS': 0, 'talks-INITIAL_FORMS': 0, 'enterprises-TOTAL_FORMS': 0, 'enterprises-INITIAL_FORMS': 0})
            response = self.client.post(url, data, HTTP_HOST='admin.localhost')
            self.assertEqual(response.status_code, 200, response.content)
            event = self.client.get('/api/v1/forums/promtour/program/').json()['days'][0]['events'][0]
            self.assertEqual((event['contact_name'], event['contact_phone']), (name, phone))

    def test_dashboard_exposes_contact_and_logo_tasks_only_with_permissions(self):
        self.client.force_login(self.director)
        response = self.client.get('/admin/', HTTP_HOST='admin.localhost')
        for title in ('Контакты маршрутов', 'Логотипы предприятий маршрутов', 'Логотипы компаний конкурса'):
            self.assertContains(response, title)
        self.assertContains(response, '/admin/forums/event/?kind__exact=route')
        self.assertContains(response, '/admin/forums/organizationlogo/?group__exact=enterprises')
        from django.contrib.auth.models import Permission
        restricted = get_user_model().objects.create_user('contacts-only', is_staff=True)
        restricted.user_permissions.add(Permission.objects.get(codename='change_event'))
        self.client.force_login(restricted)
        response = self.client.get('/admin/', HTTP_HOST='admin.localhost')
        self.assertContains(response, 'Контакты маршрутов')
        self.assertNotContains(response, 'Логотипы компаний конкурса')

    def test_first_logo_upload_immediately_exposes_clear_control(self):
        from io import BytesIO
        from tempfile import TemporaryDirectory
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        image = BytesIO()
        Image.new('RGB', (16, 16), 'white').save(image, 'PNG')
        self.client.force_login(self.director)
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            data = {'group': 'partners', 'name': 'Логотип для проверки', 'image_background': 'light', 'position': 0, 'is_published': 'on',
                    'image': SimpleUploadedFile('logo.png', image.getvalue(), content_type='image/png')}
            response = self.client.post('/admin/site-editor/object/logo/new/', data, HTTP_HOST='admin.localhost')
            self.assertEqual(response.status_code, 200)
            self.assertIn('name="image-clear"', response.json()['html'])
            logo = OrganizationLogo.objects.get(name='Логотип для проверки')
            data.pop('image')
            data.update({'image-clear': 'on', '_version': logo.updated_at.isoformat()})
            response = self.client.post(f'/admin/site-editor/object/logo/{logo.pk}/', data, HTTP_HOST='admin.localhost')
            self.assertEqual(response.status_code, 200)
            logo.refresh_from_db()
            self.assertFalse(logo.image)
            self.assertNotIn('name="image-clear"', response.json()['html'])
