import io
import json
from datetime import time
from pathlib import Path
from tempfile import TemporaryDirectory

from PIL import Image
from django.core.exceptions import ValidationError
from django.core.management import call_command, CommandError
from django.test import TestCase, override_settings
from django.utils import timezone

from forums.models import ContactCard, Event, EventDay, Forum, ForumPage, OrganizationLogo
from voting.models import Contest, Nomination, Nominee, NomineePhoto


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class Meeting13Tests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        cls.forum = Forum.objects.create(slug='promtour', title='Форум', series='promtour', status='published', starts_at=now, ends_at=now+timezone.timedelta(days=2))
        ForumPage.objects.create(forum=cls.forum)
        cls.day = EventDay.objects.create(forum=cls.forum, date=now.date())
        cls.event = Event.objects.create(day=cls.day, title='Шоу', start_time=time(11,20), end_time=time(11,30), is_published=True)
        cls.company = OrganizationLogo.objects.create(forum=cls.forum, group='events', name='Компания', show_name=False, static_image='/img/company.png')
        contest = Contest.objects.create(forum=cls.forum, title='Конкурс')
        nomination = Nomination.objects.create(contest=contest, title='Номинация')
        cls.nominee = Nominee.objects.create(nomination=nomination, name='Компания', description='Текст редактора')

    def program(self):
        return self.client.get('/api/v1/forums/promtour/program/').json()

    def test_event_company_is_public_without_adding_a_person(self):
        self.event.organizer = self.company
        self.event.save()
        payload = self.program()
        event = payload['days'][0]['events'][0]
        self.assertTrue(event['has_details'])
        self.assertEqual(event['organizer']['name'], 'Компания')
        self.assertFalse(event['organizer']['show_name'])
        self.assertEqual(payload['speakers'], [])
        self.company.is_published = False
        self.company.save()
        event = self.program()['days'][0]['events'][0]
        self.assertIsNone(event['organizer'])
        self.assertFalse(event['has_details'])

    def test_event_organizer_must_belong_to_same_forum(self):
        now = timezone.now()
        other = Forum.objects.create(slug='other', title='Другой', starts_at=now, ends_at=now+timezone.timedelta(days=1))
        company = OrganizationLogo.objects.create(forum=other, group='events', name='Чужая')
        self.event.organizer = company
        with self.assertRaises(ValidationError):
            self.event.full_clean()

    def test_contact_person_phone_and_email_are_separate_public_fields(self):
        ContactCard.objects.create(forum=self.forum, title='Связь', person_name='Иван Петров', phone='+7 (999) 123-45-67', email='public@example.org')
        contact = self.program()['page']['contacts'][0]
        self.assertEqual(contact['person_name'], 'Иван Петров')
        self.assertEqual(contact['phone'], '+7 (999) 123-45-67')
        self.assertEqual(contact['email'], 'public@example.org')

    def image(self, root):
        image = io.BytesIO(); Image.new('RGB', (24,24), 'white').save(image, 'PNG')
        Path(root, 'logo.png').write_bytes(image.getvalue())

    def run_manifest(self, root, manifest, apply=True):
        path = Path(root, 'manifest.json'); path.write_text(json.dumps(manifest))
        options = {'directory': root, 'stdout': io.StringIO()}
        if apply: options['apply'] = True
        call_command('import_forum_materials', str(path), **options)

    def test_material_import_is_idempotent_and_keeps_later_editor_changes(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            self.image(directory)
            manifest = {'forum':'promtour','batch':'test-import','logos':[{'model':'voting.nominee','id':str(self.nominee.pk),'file':'logo.png'}],
                        'galleries':[{'nominee_id':str(self.nominee.pk),'files':['logo.png'],'caption':'Компания'}]}
            self.run_manifest(directory, manifest, apply=False)
            self.nominee.refresh_from_db(); self.assertFalse(self.nominee.logo)
            self.assertEqual(NomineePhoto.objects.count(), 0)
            self.run_manifest(directory, manifest)
            self.nominee.refresh_from_db(); first = self.nominee.logo.name
            self.assertTrue(first)
            self.assertEqual(NomineePhoto.objects.count(), 1)
            self.nominee.name = 'Новое имя редактора'; self.nominee.save()
            photo = NomineePhoto.objects.get()
            from django.core.files.base import ContentFile
            renamed = photo.image.storage.save('editor/photo.png', ContentFile(Path(directory, 'logo.png').read_bytes()))
            photo.image.name = renamed
            photo.variants = {**photo.variants, '_source': renamed}
            photo.caption = 'Подпись редактора'; photo.save()
            self.run_manifest(directory, manifest)
            self.nominee.refresh_from_db(); photo.refresh_from_db()
            self.assertEqual(self.nominee.logo.name, first)
            self.assertEqual(self.nominee.name, 'Новое имя редактора')
            self.assertEqual(self.nominee.description, 'Текст редактора')
            self.assertEqual(photo.caption, 'Подпись редактора')
            self.assertEqual(NomineePhoto.objects.count(), 1)

    def test_conflicting_patch_rolls_back_prior_changes(self):
        with TemporaryDirectory() as directory:
            manifest = {'forum':'promtour','batch':'test-import','patches':[
                {'model':'forums.event','id':str(self.event.pk),'expected':{'description':''},'changes':{'description':'Новый текст'}},
                {'model':'forums.event','id':str(self.event.pk),'expected':{'contact_name':'Старая версия'},'changes':{'contact_name':'Подмена'}}]}
            with self.assertRaises(CommandError): self.run_manifest(directory, manifest)
            self.event.refresh_from_db()
            self.assertEqual(self.event.description, '')
            self.assertEqual(self.event.contact_name, '')

    def test_manifest_cannot_read_files_outside_material_directory(self):
        with TemporaryDirectory() as directory:
            manifest = {'forum':'promtour','batch':'test-import','logos':[{'model':'voting.nominee','id':str(self.nominee.pk),'file':'../outside.png'}]}
            with self.assertRaises(CommandError): self.run_manifest(directory, manifest)

    def test_time_patch_compares_serialized_time_without_overwriting_other_fields(self):
        with TemporaryDirectory() as directory:
            manifest = {'forum':'promtour','batch':'test-import','patches':[
                {'model':'forums.event','id':str(self.event.pk),'expected':{'start_time':'11:20:00'},'changes':{'start_time':'11:00:00'}}]}
            self.run_manifest(directory, manifest)
            self.event.refresh_from_db()
            self.assertEqual(self.event.start_time, time(11))
            self.assertEqual(self.event.end_time, time(11,30))
            self.assertEqual(self.event.title, 'Шоу')
