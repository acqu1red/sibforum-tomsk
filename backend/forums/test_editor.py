import io
from pathlib import Path
from tempfile import TemporaryDirectory
from datetime import time

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.admin.models import LogEntry
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from .models import Forum, ForumPage, PageSection, Venue, EventDay, Event, Speaker


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['admin.localhost', 'testserver'],
                   ADMIN_HOSTS={'admin.localhost'}, ADMIN_TOTP_REQUIRED=False)
class VisualEditorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.forum = Forum.objects.create(slug='promtour', title='Актуальный форум', starts_at=now,
            ends_at=now + timezone.timedelta(days=1), series='promtour', status='published')
        cls.page = ForumPage.objects.create(forum=cls.forum)
        cls.section = PageSection.objects.create(forum=cls.forum, key='hero', heading='Первый экран')
        cls.director = get_user_model().objects.create_user('director', is_staff=True, is_superuser=True)
        cls.viewer = get_user_model().objects.create_user('viewer', is_staff=True)
        cls.speaker = Speaker.objects.create(forum=cls.forum, full_name='Иванов Иван Иванович')

    def login(self, user=None):
        self.client.force_login(user or self.director)

    def url(self, kind='section', obj=None):
        return f'/admin/site-editor/object/{kind}/{(obj or self.section).pk}/'

    def test_non_staff_and_read_only_staff_cannot_open_or_write(self):
        self.assertEqual(self.client.get('/admin/site-editor/', HTTP_HOST='admin.localhost').status_code, 302)
        self.login(self.viewer)
        self.assertEqual(self.client.get('/admin/site-editor/', HTTP_HOST='admin.localhost').status_code, 403)
        self.assertEqual(self.client.post(self.url(), {'heading': 'forged'}, HTTP_HOST='admin.localhost').status_code, 403)

    def test_editor_is_not_available_on_public_host(self):
        self.login()
        self.assertEqual(self.client.get('/admin/site-editor/', HTTP_HOST='testserver').status_code, 404)

    def test_save_changes_public_catalog_and_records_author(self):
        self.login()
        self.assertContains(self.client.get('/admin/site-editor/', HTTP_HOST='admin.localhost'), 'Редактор сайта')
        result = self.client.post(self.url(), {'_version': self.section.updated_at.isoformat(),
            'heading': 'Новый первый экран', 'body': 'Новый текст', 'is_published': 'on'}, HTTP_HOST='admin.localhost')
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json()['saved'])
        self.section.refresh_from_db()
        self.assertEqual(self.section.heading, 'Новый первый экран')
        self.assertEqual(LogEntry.objects.get().user, self.director)
        public = self.client.get('/api/v1/forums/promtour/program/', HTTP_HOST='admin.localhost').json()
        self.assertEqual(public['page']['sections']['hero']['heading'], 'Новый первый экран')

    def test_stale_edit_does_not_overwrite_a_colleague(self):
        self.login()
        old = self.section.updated_at.isoformat()
        self.section.heading = 'Изменено коллегой'; self.section.save()
        result = self.client.post(self.url(), {'_version': old, 'heading': 'Устаревший текст'}, HTTP_HOST='admin.localhost')
        self.assertEqual(result.status_code, 409)
        self.section.refresh_from_db()
        self.assertEqual(self.section.heading, 'Изменено коллегой')

    def test_cross_forum_object_is_not_exposed(self):
        self.login()
        now = timezone.now()
        other = Forum.objects.create(slug='another', title='Другой', starts_at=now, ends_at=now+timezone.timedelta(days=1))
        section = PageSection.objects.create(forum=other, key='hero')
        self.assertEqual(self.client.get(self.url(obj=section), HTTP_HOST='admin.localhost').status_code, 404)

    def test_malformed_record_id_is_a_404(self):
        self.login()
        self.assertEqual(self.client.get('/admin/site-editor/object/section/not-a-uuid/',
                                        HTTP_HOST='admin.localhost').status_code, 404)

    def test_write_requires_csrf_even_for_director(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.director)
        self.assertEqual(client.post(self.url(), {'_version': self.section.updated_at.isoformat(),
            'heading': 'Forged request'}, HTTP_HOST='admin.localhost').status_code, 403)
        self.section.refresh_from_db()
        self.assertEqual(self.section.heading, 'Первый экран')

    def test_upload_and_account_fields_cannot_be_mass_assigned(self):
        self.login()
        r = self.client.post(self.url(), {'_version': self.section.updated_at.isoformat(), 'heading': 'Текст',
            'forum': 'forged', 'key': 'registration', 'is_superuser': 'on', 'action_url': 'javascript:alert(1)'}, HTTP_HOST='admin.localhost')
        self.assertEqual(r.status_code, 422)
        self.section.refresh_from_db()
        self.assertEqual(self.section.key, 'hero')
        self.assertEqual(self.section.heading, 'Первый экран')

    def test_speaker_form_has_all_four_photograph_placements(self):
        self.login()
        r = self.client.get(self.url('speaker', self.speaker), HTTP_HOST='admin.localhost')
        self.assertEqual(r.status_code, 200)
        for placement in ('circle', 'program', 'card', 'dialog'):
            self.assertIn('photo-'+placement+'-image', r.json()['html'])

    def test_content_editor_does_not_gain_voting_permissions(self):
        self.viewer.user_permissions.add(Permission.objects.get(codename='change_pagesection'))
        self.login(self.viewer)
        self.assertEqual(self.client.get(self.url(), HTTP_HOST='admin.localhost').status_code, 200)
        self.assertEqual(self.client.get('/admin/site-editor/object/contest/anything/', HTTP_HOST='admin.localhost').status_code, 403)

    def test_preview_uses_public_fallback_catalog_and_blocks_writes(self):
        self.login()
        with TemporaryDirectory() as directory:
            Path(directory, 'index.html').write_text('<html><head><script src="/promtour/content.js?v=123"></script>'
                '<link href="/css/style.css"></head><body></body></html>')
            with override_settings(PUBLIC_SITE_ROOT=directory, PUBLIC_SITE_URL='https://public.example.org'):
                result = self.client.get('/admin/site-editor/preview/forum/', HTTP_HOST='admin.localhost')
        self.assertContains(result, 'src="https://public.example.org/promtour/content.js?v=123"')
        self.assertContains(result, 'href="https://public.example.org/css/style.css"')
        self.assertContains(result, 'submissions_enabled:0,voting_enabled:0')
        self.assertContains(result, 'window.FORUM_EDITOR_PREVIEW=true')
        self.assertEqual(result.headers['X-Frame-Options'], 'SAMEORIGIN')
        self.assertEqual(result.headers['Content-Security-Policy'], "frame-ancestors 'self'")
