import uuid
from urllib.parse import urlparse

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Последнее изменение')

    class Meta:
        abstract = True


class Forum(TimeStampedModel):
    class Series(models.TextChoices):
        ESG = 'esg', 'Производительность и устойчивое развитие'
        PROMTOUR = 'promtour', 'Промышленный туризм'
        OTHER = 'other', 'Другая серия'

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Черновик'
        PUBLISHED = 'published', 'Опубликован'
        ARCHIVED = 'archived', 'Архив'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    slug = models.SlugField(unique=True, max_length=60, verbose_name='Адрес страницы')
    title = models.CharField(max_length=240, verbose_name='Название')
    short_title = models.CharField(max_length=120, blank=True, verbose_name='Короткое название')
    number = models.CharField(max_length=20, blank=True, verbose_name='Номер')
    series = models.CharField(max_length=20, choices=Series.choices, verbose_name='Серия форума')
    description = models.TextField(blank=True, verbose_name='Описание')
    starts_at = models.DateTimeField(verbose_name='Начало')
    ends_at = models.DateTimeField(verbose_name='Окончание')
    timezone = models.CharField(max_length=64, default='Asia/Tomsk', verbose_name='Часовой пояс')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, verbose_name='Статус')
    is_featured = models.BooleanField(default=False, verbose_name='Ближайший форум')

    class Meta:
        verbose_name = 'форум'
        verbose_name_plural = 'Форумы'
        ordering = ('starts_at', 'title')
        constraints = [
            models.CheckConstraint(condition=models.Q(ends_at__gt=models.F('starts_at')), name='forum_dates_valid'),
        ]

    def __str__(self):
        return self.short_title or self.title

    def clean(self):
        if self.ends_at and self.starts_at and self.ends_at <= self.starts_at:
            raise ValidationError({'ends_at': 'Окончание форума должно быть позже начала.'})


class Venue(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    forum = models.ForeignKey(Forum, on_delete=models.CASCADE, related_name='venues', verbose_name='Форум')
    name = models.CharField(max_length=200, verbose_name='Название')
    address = models.CharField(max_length=300, verbose_name='Адрес')
    map_url = models.URLField(blank=True, verbose_name='Ссылка на карту')
    position = models.PositiveIntegerField(default=0, verbose_name='Порядок отображения')
    is_published = models.BooleanField(default=True, verbose_name='Показать на сайте')

    class Meta:
        verbose_name = 'площадка'
        verbose_name_plural = 'Площадки'
        ordering = ('forum', 'position', 'name')

    def __str__(self):
        return self.name


class EventDay(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    forum = models.ForeignKey(Forum, on_delete=models.CASCADE, related_name='days', verbose_name='Форум')
    date = models.DateField(verbose_name='Дата')
    title = models.CharField(max_length=200, verbose_name='Название')
    position = models.PositiveIntegerField(default=0, verbose_name='Порядок отображения')

    class Meta:
        verbose_name = 'день программы'
        verbose_name_plural = 'Дни программы'
        ordering = ('forum', 'position', 'date')
        constraints = [
            models.UniqueConstraint(fields=('forum', 'date'), name='unique_forum_day_date'),
            models.UniqueConstraint(fields=('forum', 'position'), name='unique_forum_day_position'),
        ]

    def __str__(self):
        return f'{self.forum}: {self.date:%d.%m.%Y} — {self.title}'


class Event(TimeStampedModel):
    class Kind(models.TextChoices):
        PLENARY = 'plenary', 'Пленарная часть'
        SEMINAR = 'seminar', 'Практический семинар'
        SESSION = 'session', 'Сессия'
        ROUTE = 'route', 'Экскурсионный маршрут'
        EXCHANGE = 'exchange', 'Биржа субконтрактов'
        MASTERCLASS = 'masterclass', 'Мастер-класс'
        ROUNDTABLE = 'roundtable', 'Круглый стол'
        QUIZ = 'quiz', 'Квиз'
        OTHER = 'other', 'Другое'

    class RegistrationPolicy(models.TextChoices):
        NONE = 'none', 'Без регистрации'
        AUTO = 'auto', 'Автоматическое подтверждение'
        MODERATED = 'moderated', 'Ручная модерация'
        EXTERNAL = 'external', 'Внешняя регистрация'
        INVITE_ONLY = 'invite_only', 'По приглашению'

    class DetailMode(models.TextChoices):
        AUTO = 'auto', 'По наличию контента'
        SHORT = 'short', 'Только короткая карточка'
        DETAIL = 'detail', 'Подробное представление'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    day = models.ForeignKey(EventDay, on_delete=models.CASCADE, related_name='events', verbose_name='День программы')
    venue = models.ForeignKey(Venue, on_delete=models.PROTECT, related_name='events', null=True, blank=True, verbose_name='Площадка')
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.OTHER, verbose_name='Тип')
    title = models.CharField(max_length=300, verbose_name='Название')
    slug = models.SlugField(max_length=80, blank=True, verbose_name='Адрес страницы')
    speakers = models.ManyToManyField('Speaker', through='EventSpeaker', related_name='events', blank=True, verbose_name='Спикеры')
    annotation = models.TextField(blank=True, verbose_name='Краткое описание')
    description = models.TextField(blank=True, verbose_name='Описание')
    start_time = models.TimeField(verbose_name='Время начала')
    end_time = models.TimeField(verbose_name='Время окончания')
    registration_policy = models.CharField(max_length=20, choices=RegistrationPolicy.choices, default=RegistrationPolicy.NONE, verbose_name='Правила регистрации')
    detail_mode = models.CharField(max_length=20, choices=DetailMode.choices, default=DetailMode.AUTO, verbose_name='Показ подробностей')
    external_url = models.URLField(blank=True, verbose_name='Внешняя ссылка')
    is_paid = models.BooleanField(default=False, verbose_name='Платное участие')
    price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)], verbose_name='Стоимость, ₽')
    payment_note = models.CharField(max_length=300, blank=True, verbose_name='Условия оплаты')
    capacity_target = models.PositiveIntegerField(null=True, blank=True, validators=[MinValueValidator(1)], verbose_name='Количество мест')
    curator_email = models.EmailField(blank=True, verbose_name='Почта куратора')
    min_lot_selections = models.PositiveSmallIntegerField(default=0, verbose_name='Минимум лотов')
    max_lot_selections = models.PositiveSmallIntegerField(null=True, blank=True, validators=[MinValueValidator(1)], verbose_name='Максимум лотов')
    position = models.PositiveIntegerField(default=0, verbose_name='Порядок отображения')
    is_published = models.BooleanField(default=False, verbose_name='Показать на сайте')

    class Meta:
        verbose_name = 'мероприятие'
        verbose_name_plural = 'Мероприятия'
        ordering = ('day', 'start_time', 'position', 'title')
        constraints = [
            models.CheckConstraint(condition=models.Q(end_time__gt=models.F('start_time')), name='event_time_valid'),
            models.CheckConstraint(condition=models.Q(price__isnull=True) | models.Q(price__gte=0), name='event_price_not_negative'),
            models.CheckConstraint(condition=models.Q(capacity_target__isnull=True) | models.Q(capacity_target__gt=0), name='event_capacity_positive'),
            models.CheckConstraint(condition=models.Q(max_lot_selections__isnull=True) | models.Q(max_lot_selections__gte=models.F('min_lot_selections')), name='event_lot_limits_valid'),
            models.UniqueConstraint(fields=('day', 'slug'), condition=~models.Q(slug=''), name='unique_event_slug_per_day'),
        ]

    def __str__(self):
        return f'{self.start_time:%H:%M} — {self.title}'

    @property
    def forum(self):
        return self.day.forum

    @property
    def has_details(self):
        if self.detail_mode == self.DetailMode.DETAIL:
            return True
        if self.detail_mode == self.DetailMode.SHORT:
            return False
        return bool(self.description.strip())

    def clean(self):
        errors = {}
        if self.start_time and self.end_time and self.end_time <= self.start_time:
            errors['end_time'] = 'Окончание события должно быть позже начала.'
        if self.venue_id and self.day_id and self.venue.forum_id != self.day.forum_id:
            errors['venue'] = 'Площадка должна принадлежать тому же форуму.'
        if self.registration_policy == self.RegistrationPolicy.EXTERNAL:
            parsed = urlparse(self.external_url)
            if parsed.scheme != 'https' or not parsed.netloc:
                errors['external_url'] = 'Для внешней регистрации нужна ссылка https.'
        if self.is_paid:
            if self.price is None:
                errors['price'] = 'Укажите цену платного события.'
            if not self.payment_note.strip():
                errors['payment_note'] = 'Объясните порядок оплаты.'
        elif self.price is not None:
            errors['price'] = 'У бесплатного события не должно быть цены.'
        if self.kind == self.Kind.EXCHANGE:
            if self.registration_policy != self.RegistrationPolicy.NONE and self.min_lot_selections < 1:
                errors['min_lot_selections'] = 'Для записи на биржу нужен минимум один лот.'
            if self.max_lot_selections is not None and self.max_lot_selections < self.min_lot_selections:
                errors['max_lot_selections'] = 'Максимум лотов не может быть меньше минимума.'
        elif self.min_lot_selections or self.max_lot_selections is not None:
            errors['min_lot_selections'] = 'Лоты доступны только для биржи субконтрактов.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class ChoiceGroup(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    day = models.ForeignKey(EventDay, on_delete=models.CASCADE, related_name='choice_groups', verbose_name='День программы')
    title = models.CharField(max_length=200, verbose_name='Название')
    min_selections = models.PositiveSmallIntegerField(default=0, validators=[MinValueValidator(0)], verbose_name='Минимум вариантов')
    max_selections = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1)], verbose_name='Максимум вариантов')
    position = models.PositiveIntegerField(default=0, verbose_name='Порядок отображения')
    events = models.ManyToManyField(Event, through='ChoiceGroupEvent', related_name='choice_groups', verbose_name='Мероприятия')

    class Meta:
        verbose_name = 'группа выбора'
        verbose_name_plural = 'Правила выбора мероприятий'
        ordering = ('day', 'position', 'title')
        constraints = [
            models.CheckConstraint(condition=models.Q(min_selections__gte=0), name='choice_group_min_not_negative'),
            models.CheckConstraint(condition=models.Q(max_selections__gte=1), name='choice_group_max_positive'),
            models.CheckConstraint(condition=models.Q(max_selections__gte=models.F('min_selections')), name='choice_group_limits_valid'),
        ]

    def __str__(self):
        return f'{self.day}: {self.title}'

    def clean(self):
        if self.max_selections is not None and self.min_selections is not None and self.max_selections < self.min_selections:
            raise ValidationError({'max_selections': 'Максимум не может быть меньше минимума.'})


class ChoiceGroupEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    group = models.ForeignKey(ChoiceGroup, on_delete=models.CASCADE, related_name='event_links', verbose_name='Группа выбора')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='group_links', verbose_name='Мероприятие')
    position = models.PositiveIntegerField(default=0, verbose_name='Порядок отображения')

    class Meta:
        verbose_name = 'мероприятие группы'
        verbose_name_plural = 'Мероприятия группы'
        ordering = ('group', 'position', 'event__start_time')
        constraints = [
            models.UniqueConstraint(fields=('group', 'event'), name='unique_event_in_choice_group'),
        ]

    def __str__(self):
        return f'{self.group} — {self.event}'

    def clean(self):
        if self.group_id and self.event_id and self.group.day_id != self.event.day_id:
            raise ValidationError({'event': 'Событие должно принадлежать тому же дню, что и группа выбора.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class Speaker(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    forum = models.ForeignKey(Forum, on_delete=models.CASCADE, related_name='speakers', verbose_name='Форум')
    full_name = models.CharField(max_length=240, verbose_name='ФИО')
    credentials = models.TextField('Должность и регалии', blank=True)
    topic = models.TextField(blank=True, verbose_name='Тема выступления')
    photo = models.ImageField(upload_to='speakers/', blank=True, max_length=300, verbose_name='Фотография')
    static_photo = models.CharField(max_length=300, blank=True, help_text='Путь к фотографии на сайте, например /img/promtour/speakers/name.webp.', verbose_name='Готовое фото из материалов форума')
    position = models.PositiveIntegerField(default=0, verbose_name='Порядок отображения')
    is_published = models.BooleanField(default=True, verbose_name='Показать на сайте')

    class Meta:
        verbose_name = 'спикер'
        verbose_name_plural = 'Спикеры'
        ordering = ('forum', 'position', 'full_name')
        constraints = [
            models.UniqueConstraint(fields=('forum', 'full_name'), name='unique_speaker_name_per_forum'),
        ]

    def __str__(self):
        return self.full_name

    @property
    def photo_url(self):
        return self.photo.url if self.photo else self.static_photo

    def clean(self):
        if self.static_photo:
            parsed = urlparse(self.static_photo)
            local_path = self.static_photo.startswith('/') and not self.static_photo.startswith('//')
            if not local_path and not (parsed.scheme == 'https' and parsed.netloc):
                raise ValidationError({'static_photo': 'Укажите путь на этом сайте или ссылку https.'})


class EventSpeaker(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='speaker_links', verbose_name='Мероприятие')
    speaker = models.ForeignKey(Speaker, on_delete=models.CASCADE, related_name='event_links', verbose_name='Спикер')
    role = models.CharField(max_length=120, default='Спикер', verbose_name='Роль')
    topic = models.TextField(blank=True, verbose_name='Тема выступления')
    position = models.PositiveIntegerField(default=0, verbose_name='Порядок отображения')

    class Meta:
        verbose_name = 'выступление спикера'
        verbose_name_plural = 'Выступления спикеров'
        ordering = ('event', 'position', 'speaker__full_name')
        constraints = [
            models.UniqueConstraint(fields=('event', 'speaker'), name='unique_speaker_per_event'),
        ]

    def __str__(self):
        return f'{self.speaker} — {self.event}'

    def clean(self):
        if self.event_id and self.speaker_id and self.event.day.forum_id != self.speaker.forum_id:
            raise ValidationError({'speaker': 'Спикер должен принадлежать тому же форуму.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class RouteEnterprise(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='enterprises', verbose_name='Мероприятие')
    name = models.CharField(max_length=300, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    position = models.PositiveIntegerField(default=0, verbose_name='Порядок отображения')

    class Meta:
        verbose_name = 'предприятие маршрута'
        verbose_name_plural = 'Предприятия маршрутов'
        ordering = ('event', 'position', 'name')

    def __str__(self):
        return self.name

    def clean(self):
        if self.event_id and self.event.kind != Event.Kind.ROUTE:
            raise ValidationError({'event': 'Предприятия можно добавлять только к экскурсионному маршруту.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)
