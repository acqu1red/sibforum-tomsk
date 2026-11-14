from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.test import TestCase, override_settings
from django.utils import timezone

from forums.editor import related_forms
from forums.models import Forum, ForumPage, ContactCard
from .admin import NomineePhotoInline
from .forms import NomineePhotoFormSet
from .models import Contest, Nomination, Nominee, NomineePhoto


@override_settings(SECURE_SSL_REDIRECT=False, ALLOWED_HOSTS=['testserver'])
class GalleryEditorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        now=timezone.now()
        cls.forum=Forum.objects.create(slug='gallery',title='Форум',starts_at=now,ends_at=now+timezone.timedelta(days=2),status='published')
        ForumPage.objects.create(forum=cls.forum)
        contest=Contest.objects.create(forum=cls.forum,title='Конкурс')
        nomination=Nomination.objects.create(contest=contest,title='Номинация')
        cls.nominee=Nominee.objects.create(nomination=nomination,name='Компания в списке',detail_title='Заголовок проекта',description='Общий текст\nВторой абзац')
        cls.admin=get_user_model().objects.create_superuser('editor','editor@example.org','test-only')

    def setUp(self):
        directory=TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        override=override_settings(MEDIA_ROOT=directory.name)
        override.enable();self.addCleanup(override.disable)
        self.media=Path(directory.name);(self.media/'photos').mkdir()

    def bound(self, count, delete=None, admin=False):
        for n in range(count):
            Image.new('RGB',(8,8),'white').save(self.media/f'photos/{n}.png')
            NomineePhoto.objects.create(nominee=self.nominee,image=f'photos/{n}.png',variants={'_source':f'photos/{n}.png'},caption=f'Описание {n}\nВторая строка')
        photos=list(self.nominee.photos.all());data={'gallery-TOTAL_FORMS':str(count),'gallery-INITIAL_FORMS':str(count),'gallery-MAX_NUM_FORMS':'10','gallery-MIN_NUM_FORMS':'0'}
        for i,p in enumerate(photos):
            data.update({f'gallery-{i}-id':str(p.pk),f'gallery-{i}-caption':p.caption,f'gallery-{i}-position':str(i),f'gallery-{i}-nominee':str(self.nominee.pk)})
            if i==delete:data[f'gallery-{i}-DELETE']='on'
        if admin:
            factory=inlineformset_factory(Nominee,NomineePhoto,formset=NomineePhotoInline.formset,fields=['image','caption','position'],extra=0,can_delete=True,max_num=10)
            return factory(data=data,instance=self.nominee,prefix='gallery')
        return related_forms('nominee',self.nominee,self.forum,self.admin,data=data)[0]['formset']

    def test_both_editors_accept_ten_photos_with_independent_descriptions(self):
        formset=self.bound(10)
        self.assertTrue(formset.is_valid(),formset.errors)
        self.assertEqual(len(formset.forms),10)
        self.assertEqual(formset.forms[2].cleaned_data['caption'],'Описание 2\nВторая строка')

    def test_visual_editor_rejects_eleven_photos(self):
        formset=self.bound(11)
        self.assertFalse(formset.is_valid());self.assertTrue(formset.non_form_errors())

    def test_admin_also_rejects_forged_eleven_photo_submission(self):
        formset=self.bound(11,admin=True)
        self.assertFalse(formset.is_valid());self.assertIn('10 фотографий',str(formset.non_form_errors()))

    def test_marking_an_excess_photo_for_deletion_allows_saving(self):
        formset=self.bound(11,delete=4)
        self.assertTrue(formset.is_valid(),formset.non_form_errors());formset.save()
        self.assertEqual(self.nominee.photos.count(),10)

    def test_api_keeps_list_name_separate_from_dialog_title_and_general_description(self):
        self.bound(2)
        data=self.client.get('/api/v1/contests/gallery/').json()['nominations'][0]['nominees'][0]
        self.assertEqual(data['name'],'Компания в списке')
        self.assertEqual(data['detail_title'],'Заголовок проекта')
        self.assertEqual(data['description'],'Общий текст\nВторой абзац')
        self.assertEqual(len(data['photos']),2)
        self.assertEqual(data['photos'][0]['caption'],'Описание 0\nВторая строка')

    def test_contact_placement_is_public_and_hidden_contacts_stay_hidden(self):
        contact=ContactCard.objects.create(forum=self.forum,placement='organizers',title='По вопросам Форума обращаться',person_name='Иван Тестовый',phone='+79990000000')
        data=self.client.get('/api/v1/forums/gallery/program/').json()['page']['contacts']
        self.assertEqual(data[0]['placement'],'organizers');self.assertEqual(data[0]['person_name'],'Иван Тестовый')
        contact.is_published=False;contact.save()
        self.assertEqual(self.client.get('/api/v1/forums/gallery/program/').json()['page']['contacts'],[])
