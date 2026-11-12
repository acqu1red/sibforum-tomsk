import uuid

from django.core.validators import MaxValueValidator
from django.db import models

from .media import image_variants, safe_public_link, validate_image_upload
from .models import Forum, Speaker, TimeStampedModel, Venue
from .interface import TEXT_CHOICES


class ContentRevision(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    token = models.UUIDField(default=uuid.uuid4, editable=False)

    class Meta:
        verbose_name = 'версия содержания'
        verbose_name_plural = 'Версии содержания'


class InterfaceText(TimeStampedModel):
    forum = models.ForeignKey(Forum, on_delete=models.CASCADE, related_name='interface_texts', verbose_name='Форум')
    key = models.CharField('Место на сайте', max_length=60, choices=TEXT_CHOICES)
    value = models.TextField('Текст', blank=True, help_text='Оставьте пустым, чтобы убрать пояснение. Ограничения выбора от этого не меняются.')

    class Meta:
        verbose_name = 'подпись или пояснение'
        verbose_name_plural = 'Подписи и пояснения'
        constraints = [models.UniqueConstraint(fields=('forum', 'key'), name='unique_interface_text')]

    def __str__(self):
        return self.get_key_display()


class ForumPage(TimeStampedModel):
    forum = models.OneToOneField(Forum, on_delete=models.CASCADE, related_name='page', verbose_name='Форум')
    brand_name = models.CharField('Название в шапке', max_length=120, default='Промышленный туризм')
    brand_subtitle = models.CharField('Подпись в шапке', max_length=120, default='Сибирский форум')
    brand_logo = models.ImageField('Логотип в шапке', upload_to='page/', blank=True, validators=[validate_image_upload])
    brand_static_logo = models.CharField('Готовый логотип в шапке', max_length=300, blank=True, default='/img/brand/tpp-tomsk-logo-white.png', validators=[safe_public_link])
    brand_variants = models.JSONField(default=dict, editable=False)
    date_label = models.CharField('Даты и город на первом экране', max_length=160, blank=True, help_text='Оставьте пустым, чтобы брать даты из форума.')
    main_venue = models.ForeignKey(Venue, verbose_name='Основная площадка', on_delete=models.SET_NULL, null=True, blank=True)
    venue_label = models.CharField('Подпись над площадкой', max_length=160, default='Основная деловая площадка')
    venue_note = models.CharField('Время / пояснение площадки', max_length=200, blank=True)
    organizer_email = models.EmailField('Почта организатора', blank=True)
    footer_text = models.CharField('Подпись внизу сайта', max_length=300, blank=True)
    hero_image = models.ImageField('Фотография первого экрана', upload_to='page/', blank=True, validators=[validate_image_upload])
    hero_static_image = models.CharField('Готовое изображение первого экрана', max_length=300, blank=True, validators=[safe_public_link])
    hero_variants = models.JSONField(default=dict, editable=False)
    registration_notice = models.TextField('Сообщение при закрытой регистрации', default='Приём заявок временно недоступен. Программа и описание маршрутов доступны для просмотра.')
    initialized = models.BooleanField(default=False, editable=False)
    meeting_revision = models.CharField(max_length=40, blank=True, editable=False)
    reference_logos_imported = models.BooleanField(default=False, editable=False)
    meeting_12_organizations_applied = models.BooleanField(default=False, editable=False)

    class Meta:
        verbose_name = 'страница форума'
        verbose_name_plural = 'Страница сайта'

    def __str__(self):
        return f'Страница: {self.forum}'

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.main_venue_id and self.main_venue.forum_id != self.forum_id:
            raise ValidationError({'main_venue': 'Выберите площадку этого форума.'})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        variants = image_variants(self.hero_image, self.hero_variants)
        if variants != self.hero_variants:
            self.hero_variants = variants
            type(self).objects.filter(pk=self.pk).update(hero_variants=variants)
        variants = image_variants(self.brand_logo, self.brand_variants)
        if variants != self.brand_variants:
            self.brand_variants = variants
            type(self).objects.filter(pk=self.pk).update(brand_variants=variants)


SECTION_CHOICES = (
    ('hero', 'Первый экран'), ('speakers', 'Спикеры перед программой'),
    ('program', 'Программа'), ('routes', 'Экскурсионные маршруты'),
    ('exchange', 'Биржа субконтрактации'), ('contest', 'Конкурс'),
    ('registration', 'Регистрация'), ('contacts', 'Контакты'),
    ('organizers', 'Организаторы'), ('partners', 'Партнёры форума'),
    ('enterprises', 'Промтуризм в Томске'),
)


class PageSection(TimeStampedModel):
    forum = models.ForeignKey(Forum, on_delete=models.CASCADE, related_name='page_sections', verbose_name='Форум')
    key = models.CharField('Раздел', max_length=30, choices=SECTION_CHOICES)
    heading = models.CharField('Заголовок', max_length=300, blank=True)
    eyebrow = models.CharField('Короткая подпись над заголовком', max_length=200, blank=True)
    body = models.TextField('Описание', blank=True)
    note = models.TextField('Дополнительное пояснение', blank=True)
    action_label = models.CharField('Надпись на кнопке', max_length=120, blank=True)
    action_url = models.CharField('Куда ведёт кнопка', max_length=500, blank=True, validators=[safe_public_link])
    is_published = models.BooleanField('Показать раздел', default=True)

    class Meta:
        verbose_name = 'текст раздела'
        verbose_name_plural = 'Тексты разделов'
        constraints = [models.UniqueConstraint(fields=('forum', 'key'), name='unique_page_section')]

    def __str__(self):
        return self.get_key_display()


class NavigationItem(TimeStampedModel):
    forum = models.ForeignKey(Forum, on_delete=models.CASCADE, related_name='navigation', verbose_name='Форум')
    label = models.CharField('Подпись', max_length=120)
    target = models.CharField('Ссылка', max_length=500, validators=[safe_public_link], help_text='Например /#program, /#exchange или /contest/.')
    position = models.PositiveIntegerField('Порядок', default=0)
    is_published = models.BooleanField('Показать в меню', default=True)

    class Meta:
        verbose_name = 'пункт меню'
        verbose_name_plural = 'Меню сайта'
        ordering = ('position', 'pk')

    def __str__(self):
        return self.label


class ContactCard(TimeStampedModel):
    forum = models.ForeignKey(Forum, on_delete=models.CASCADE, related_name='contact_cards', verbose_name='Форум')
    venue = models.ForeignKey(Venue, on_delete=models.SET_NULL, related_name='contact_cards', null=True, blank=True, verbose_name='Площадка', help_text='Название и адрес площадки подставятся автоматически. Для обычного контакта оставьте пустым.')
    title = models.CharField('Название', max_length=200, blank=True, help_text='Для площадки можно оставить пустым: возьмём её название.')
    subtitle = models.CharField('Короткая подпись', max_length=200, blank=True)
    body = models.TextField('Адрес и пояснения', blank=True)
    link_label = models.CharField('Подпись ссылки', max_length=120, blank=True)
    link_url = models.CharField('Ссылка', max_length=500, blank=True, validators=[safe_public_link])
    position = models.PositiveIntegerField('Порядок', default=0)
    is_published = models.BooleanField('Показать на сайте', default=True)

    class Meta:
        verbose_name = 'контактная карточка'
        verbose_name_plural = 'Контакты сайта'
        ordering = ('position', 'pk')

    def __str__(self):
        return self.title or (self.venue.name if self.venue else 'Контакт')

    def clean(self):
        from django.core.exceptions import ValidationError
        errors = {}
        if not self.title and not self.venue_id:
            errors['title'] = 'Укажите название или выберите площадку.'
        if self.venue_id and self.venue.forum_id != self.forum_id:
            errors['venue'] = 'Выберите площадку этого форума.'
        if errors:
            raise ValidationError(errors)


class OrganizationLogo(TimeStampedModel):
    GROUPS = (('organizers', 'Организаторы'), ('partners', 'Партнёры форума'), ('enterprises', 'Промтуризм в Томске'))
    forum = models.ForeignKey(Forum, on_delete=models.CASCADE, related_name='organization_logos', verbose_name='Форум')
    route_enterprise = models.ForeignKey('RouteEnterprise', on_delete=models.SET_NULL, null=True, blank=True, related_name='logos', verbose_name='Предприятие маршрута', help_text='Для группы «Промтуризм в Томске» выберите предприятие из действующей программы.')
    group = models.CharField('Группа', choices=GROUPS, max_length=20)
    name = models.CharField('Организация', max_length=240)
    image = models.ImageField('Логотип', upload_to='logos/', blank=True, validators=[validate_image_upload])
    static_image = models.CharField('Готовое изображение на сайте', max_length=300, blank=True, validators=[safe_public_link])
    image_background = models.CharField('Фон под логотипом', max_length=10,
        choices=(('light', 'Светлый — для цветных и тёмных логотипов'), ('dark', 'Синий — для белых логотипов')), default='light')
    website_url = models.URLField('Сайт организации', blank=True)
    position = models.PositiveIntegerField('Порядок', default=0)
    is_published = models.BooleanField('Показать на сайте', default=True)
    variants = models.JSONField(default=dict, editable=False)

    class Meta:
        verbose_name = 'логотип организации'
        verbose_name_plural = 'Организаторы, партнёры и предприятия'
        ordering = ('group', 'position', 'name')

    def __str__(self):
        return f'{self.name} · {self.get_group_display()}'

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.route_enterprise_id and self.route_enterprise.event.day.forum_id != self.forum_id:
            raise ValidationError({'route_enterprise': 'Выберите предприятие этого форума.'})
        if self.group == 'enterprises' and not self.route_enterprise_id:
            raise ValidationError({'route_enterprise': 'Выберите предприятие маршрута или другую группу организаций.'})

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        variants = image_variants(self.image, self.variants)
        if variants != self.variants:
            self.variants = variants
            type(self).objects.filter(pk=self.pk).update(variants=variants)


class SpeakerPhoto(TimeStampedModel):
    PLACEMENTS = (('circle', 'Круг перед программой'), ('program', 'Круг в программе'), ('card', 'Карточка в списке'), ('dialog', 'Подробная карточка'))
    speaker = models.ForeignKey(Speaker, on_delete=models.CASCADE, related_name='photo_placements', verbose_name='Спикер')
    placement = models.CharField('Место на сайте', max_length=20, choices=PLACEMENTS)
    image = models.ImageField('Отдельная фотография', upload_to='speakers/placements/', blank=True, validators=[validate_image_upload], help_text='Необязательно. Без отдельного файла используется общая фотография спикера.')
    fit = models.CharField('Как показывать', max_length=10, choices=(('cover', 'Заполнить область'), ('contain', 'Показать фотографию целиком')), default='cover')
    focal_x = models.PositiveSmallIntegerField('Фокус по горизонтали, %', default=50, validators=[MaxValueValidator(100)])
    focal_y = models.PositiveSmallIntegerField('Фокус по вертикали, %', default=25, validators=[MaxValueValidator(100)])
    variants = models.JSONField(default=dict, editable=False)

    class Meta:
        verbose_name = 'вариант фотографии'
        verbose_name_plural = 'Варианты фотографии'
        constraints = [models.UniqueConstraint(fields=('speaker', 'placement'), name='unique_speaker_photo_placement')]

    def __str__(self):
        return self.get_placement_display()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        variants = image_variants(self.image, self.variants)
        if variants != self.variants:
            self.variants = variants
            type(self).objects.filter(pk=self.pk).update(variants=variants)
