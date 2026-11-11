import io
import tempfile
from datetime import time

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from .content import speaker_photos
from .models import ContactCard, Event, EventDay, Forum, ForumPage, PageSection, Speaker, SpeakerPhoto


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'], ADMIN_TOTP_REQUIRED=False)
class EditorialContentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.forum = Forum.objects.create(slug='promtour', title='Форум', starts_at=now, ends_at=now+timezone.timedelta(days=1), status='published')
        cls.speaker = Speaker.objects.create(forum=cls.forum, full_name='Беленок Ирина Александровна', static_photo='/img/promtour/speakers/belenok.webp')

    def test_editorial_fields_are_live_and_empty_text_stays_empty(self):
        ForumPage.objects.create(forum=self.forum, brand_name='Новое название')
        section = PageSection.objects.create(forum=self.forum, key='program', heading='Новая программа', body='Текст')
        ContactCard.objects.create(forum=self.forum, title='Опубликованная площадка')
        ContactCard.objects.create(forum=self.forum, title='Скрытая площадка', is_published=False)
        data = self.client.get('/api/v1/forums/promtour/program/').json()
        self.assertEqual(data['page']['brand_name'], 'Новое название')
        self.assertEqual(data['page']['sections']['program']['heading'], 'Новая программа')
        self.assertEqual(len(data['page']['contacts']), 1)
        section.body = ''
        section.save()
        data = self.client.get('/api/v1/forums/promtour/program/').json()
        self.assertEqual(data['page']['sections']['program']['body'], '')
        self.assertIn('no-cache', self.client.get('/api/v1/forums/promtour/program/')['Cache-Control'])

    def test_revision_changes_after_saved_content_commits(self):
        before = self.client.get('/api/v1/content-revision/').json()['revision']
        with self.captureOnCommitCallbacks(execute=True):
            self.speaker.short_name = 'Ирина Беленок'
            self.speaker.save()
        after = self.client.get('/api/v1/content-revision/').json()['revision']
        self.assertNotEqual(before, after)

    def test_photo_inheritance_and_per_placement_focus(self):
        SpeakerPhoto.objects.create(speaker=self.speaker, placement='circle', fit='contain', focal_x=30, focal_y=70)
        photos = speaker_photos(self.speaker)
        self.assertEqual(photos['circle']['x'], 30)
        self.assertEqual(photos['circle']['fit'], 'contain')
        self.assertEqual(photos['dialog']['fit'], 'contain')
        self.assertTrue(photos['circle']['url'].endswith('-320.webp'))
        self.assertEqual(self.speaker.display_name, 'Ирина Беленок')

    def test_uploaded_photo_has_small_derivatives_and_keeps_original(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            image = Image.new('RGB', (2000, 1000), '#c9d6ed')
            raw = io.BytesIO(); image.save(raw, 'JPEG')
            self.speaker.photo = SimpleUploadedFile('portrait.jpg', raw.getvalue(), content_type='image/jpeg')
            self.speaker.save()
            self.speaker.refresh_from_db()
            self.assertTrue(self.speaker.photo.storage.exists(self.speaker.photo.name))
            self.assertIn('160', self.speaker.photo_variants)
            derivative = self.speaker.photo_variants['400'].removeprefix('/media/')
            with self.speaker.photo.storage.open(derivative) as file, Image.open(file) as result:
                self.assertLessEqual(max(result.size), 400)
            SpeakerPhoto.objects.create(speaker=self.speaker, placement='dialog', image=SimpleUploadedFile('other.jpg', raw.getvalue(), content_type='image/jpeg'))
            photos = speaker_photos(self.speaker)
            self.assertTrue(photos['dialog']['url'].endswith('400.webp'))

    def test_public_preview_requires_fresh_signed_staff_permission(self):
        user = get_user_model().objects.create_user('previewer', is_staff=True)
        token = signing.dumps({'user': user.pk}, salt='registration-preview')
        self.assertEqual(self.client.get('/api/v1/registration-preview/', {'token': token}).status_code, 403)
        user.is_superuser = True; user.save()
        self.assertEqual(self.client.get('/api/v1/registration-preview/', {'token': token}).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/registration-preview/', {'token': 'invalid'}).status_code, 403)

    def test_initialization_never_restores_removed_or_changed_content(self):
        from django.core.management import call_command
        call_command('initialize_forum_page', verbosity=0)
        section = PageSection.objects.get(forum=self.forum, key='hero')
        section.heading = 'Исправлено организатором'; section.save()
        ContactCard.objects.filter(forum=self.forum).delete()
        call_command('initialize_forum_page', verbosity=0)
        section.refresh_from_db()
        self.assertEqual(section.heading, 'Исправлено организатором')
        self.assertEqual(ContactCard.objects.filter(forum=self.forum).count(), 0)

    def test_contest_title_has_one_source_on_both_pages(self):
        from voting.models import Contest
        ForumPage.objects.create(forum=self.forum)
        PageSection.objects.create(forum=self.forum, key='contest', heading='Старое название')
        Contest.objects.create(forum=self.forum, title='Новое название конкурса', description='Новое описание')
        program = self.client.get('/api/v1/forums/promtour/program/').json()
        contest = self.client.get('/api/v1/contests/promtour/').json()
        self.assertEqual(program['page']['sections']['contest']['heading'], contest['title'])
        self.assertEqual(program['page']['sections']['contest']['body'], contest['description'])

    def test_unsafe_editorial_links_are_rejected(self):
        from django.core.exceptions import ValidationError
        from .models import NavigationItem
        item = NavigationItem(forum=self.forum, label='Ссылка', target='javascript:alert(1)')
        with self.assertRaises(ValidationError):
            item.full_clean()

    def test_hidden_sections_do_not_leak_draft_text(self):
        ForumPage.objects.create(forum=self.forum)
        PageSection.objects.create(forum=self.forum, key='program', heading='Секретный черновик', body='До публикации', is_published=False)
        response = self.client.get('/api/v1/forums/promtour/program/')
        self.assertNotIn('Секретный', response.content.decode())
        self.assertEqual(response.json()['page']['sections']['program'], {'is_published': False})
