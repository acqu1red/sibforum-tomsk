from io import BytesIO
from tempfile import TemporaryDirectory
from datetime import time

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from .models import Event, EventDay, Forum, ForumPage, OrganizationLogo, RouteEnterprise


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver', 'admin.localhost'],
                   ADMIN_HOSTS=['admin.localhost'], ADMIN_TOTP_REQUIRED=False)
class OrganizationEditorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.forum = Forum.objects.create(slug='promtour', title='Форум', status='published', starts_at=now, ends_at=now + timezone.timedelta(days=2))
        ForumPage.objects.create(forum=cls.forum)
        day = EventDay.objects.create(forum=cls.forum, date=now.date())
        route = Event.objects.create(day=day, kind='route', title='Маршрут', start_time=time(9), end_time=time(12), is_published=True)
        cls.enterprise = RouteEnterprise.objects.create(event=route, name='Предприятие маршрута')
        cls.user = get_user_model().objects.create_user('editor', is_staff=True, is_superuser=True)

    def setUp(self):
        self.client.force_login(self.user)
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def image(self):
        raw = BytesIO()
        Image.new('RGBA', (24, 24), (30, 90, 200, 255)).save(raw, 'PNG')
        return SimpleUploadedFile('logo.png', raw.getvalue(), content_type='image/png')

    def test_list_save_ignores_missing_relationship_on_legacy_rows(self):
        legacy = OrganizationLogo.objects.create(forum=self.forum, group='enterprises', name='Старая запись без привязки', is_published=False)
        partner = OrganizationLogo.objects.create(forum=self.forum, group='partners', name='Партнёр')
        data = {'form-TOTAL_FORMS': '2', 'form-INITIAL_FORMS': '2', 'form-MAX_NUM_FORMS': '1000', '_save': 'Сохранить',
                'form-0-id': legacy.pk, 'form-0-position': '0', 'form-1-id': partner.pk, 'form-1-position': '9', 'form-1-is_published': 'on'}
        response = self.client.post('/admin/forums/organizationlogo/', data, HTTP_HOST='admin.localhost')
        self.assertEqual(response.status_code, 302)
        partner.refresh_from_db()
        self.assertEqual(partner.position, 9)
        legacy.refresh_from_db()
        self.assertFalse(legacy.is_published)

    def test_both_editors_create_each_group_with_image(self):
        for editor in ('visual', 'standard'):
            for group in ('organizers', 'partners', 'enterprises'):
                with self.subTest(editor=editor, group=group):
                    name = f'Проверка {editor} {group}'
                    data = {'forum': self.forum.pk, 'group': group, 'name': name, 'image': self.image(),
                            'image_background': 'light', 'position': '7', 'is_published': 'on', 'show_name': 'on', '_save': 'Сохранить'}
                    if group == 'enterprises':
                        data['route_enterprise'] = self.enterprise.pk
                    url = '/admin/site-editor/object/logo/new/' if editor == 'visual' else '/admin/forums/organizationlogo/add/'
                    response = self.client.post(url, data, HTTP_HOST='admin.localhost')
                    self.assertEqual(response.status_code, 200 if editor == 'visual' else 302, response.content[:500])
                    logo = OrganizationLogo.objects.get(name=name)
                    self.assertTrue(logo.variants.get('400'))
                    payload = self.client.get('/api/v1/forums/promtour/program/').json()['page']['logos']
                    self.assertIn(str(logo.pk), [entry['id'] for entry in payload])

    def test_missing_enterprise_returns_field_error_in_both_editors(self):
        for url, status in [('/admin/site-editor/object/logo/new/', 422), ('/admin/forums/organizationlogo/add/', 200)]:
            response = self.client.post(url, {'forum': self.forum.pk, 'group': 'enterprises', 'name': 'Без привязки',
                'image_background': 'light', 'position': '0', 'is_published': 'on'}, HTTP_HOST='admin.localhost')
            self.assertEqual(response.status_code, status)
            html = response.json()['html'] if status == 422 else response.content.decode()
            self.assertIn('Выберите предприятие маршрута', html)
        self.assertFalse(OrganizationLogo.objects.filter(name='Без привязки').exists())

    def test_builtin_header_uses_emblem_without_overwriting_custom_logo(self):
        page = self.forum.page
        data = self.client.get('/api/v1/forums/promtour/program/').json()['page']
        self.assertEqual(data['brand_logo'], '/img/brand/tpp-emblem-white.svg')
        page.brand_static_logo = '/img/custom.png'
        page.save()
        self.assertEqual(self.client.get('/api/v1/forums/promtour/program/').json()['page']['brand_logo'], '/img/custom.png')
