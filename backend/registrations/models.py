import uuid
from urllib.parse import urlparse

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from forums.models import Event, Forum, TimeStampedModel


class Participant(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    forum = models.ForeignKey(Forum, on_delete=models.PROTECT, related_name='participants', verbose_name='Форум')
    last_name = models.CharField(max_length=100, verbose_name='Фамилия')
    first_name = models.CharField(max_length=100, verbose_name='Имя')
    middle_name = models.CharField(max_length=100, verbose_name='Отчество')
    email = models.EmailField(verbose_name='Электронная почта')
    phone = models.CharField(max_length=11, verbose_name='Телефон')
    organization = models.CharField(max_length=200, verbose_name='Организация')
    position = models.CharField(max_length=200, verbose_name='Должность')
    category = models.CharField(max_length=60, verbose_name='Категория участника')
    city = models.CharField(max_length=100, blank=True, verbose_name='Город')
    source = models.CharField(max_length=100, blank=True, verbose_name='Источник информации о форуме')
    comment = models.TextField(blank=True, max_length=1000, verbose_name='Комментарий')

    class Meta:
        verbose_name = 'участник'
        verbose_name_plural = 'Участники'
        ordering = ('last_name', 'first_name', 'middle_name')
        constraints = [
            models.UniqueConstraint(fields=('forum', 'email'), name='unique_participant_email_per_forum'),
        ]

    @property
    def full_name(self):
        return ' '.join(part for part in (self.last_name, self.first_name, self.middle_name) if part)

    def __str__(self):
        return f'{self.full_name} — {self.forum}'


class Registration(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    participant = models.OneToOneField(Participant, on_delete=models.PROTECT, related_name='registration', verbose_name='Участник')
    email_verified_at = models.DateTimeField(null=True, blank=True, verbose_name='Почта подтверждена')
    access_token_hash = models.CharField(max_length=64, blank=True, verbose_name='Защищённая личная ссылка')
    token_issued_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата выдачи личной ссылки')
    version = models.PositiveIntegerField(default=1, verbose_name='Версия')

    class Meta:
        verbose_name = 'заявка'
        verbose_name_plural = 'Заявки'
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.participant.full_name} — {self.participant.forum}'

    @property
    def email_verified(self):
        return self.email_verified_at is not None


class EmailChallenge(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    registration = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name='email_challenges', verbose_name='Заявка')
    code_hash = models.CharField(max_length=256, verbose_name='Защищённый код подтверждения')
    pending_person = models.JSONField(default=dict, verbose_name='Данные до подтверждения')
    pending_selection = models.JSONField(default=list, verbose_name='Выбор до подтверждения')
    expires_at = models.DateTimeField(verbose_name='Действует до')
    attempts = models.PositiveSmallIntegerField(default=0, verbose_name='Количество попыток')
    verified_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата подтверждения')

    class Meta:
        verbose_name = 'подтверждение почты'
        verbose_name_plural = 'Подтверждения почты'
        ordering = ('-created_at',)

    def set_code(self, code):
        self.code_hash = make_password(code)

    def check_code(self, code):
        if self.verified_at is not None or self.attempts >= 5 or self.expires_at <= timezone.now():
            return False
        self.attempts = models.F('attempts') + 1
        self.save(update_fields=('attempts', 'updated_at'))
        self.refresh_from_db(fields=('attempts',))
        return check_password(code, self.code_hash)


class RegistrationItem(TimeStampedModel):
    class Status(models.TextChoices):
        CONFIRMED = 'confirmed', 'Подтверждено'
        PENDING_REVIEW = 'pending_review', 'На рассмотрении'
        APPROVED = 'approved', 'Одобрено модератором'
        REJECTED = 'rejected', 'Отклонено'
        CANCELLED_BY_USER = 'cancelled_by_user', 'Отменено участником'
        CANCELLED_BY_ADMIN = 'cancelled_by_admin', 'Отменено администратором'

    ACTIVE_STATUSES = (Status.CONFIRMED, Status.PENDING_REVIEW, Status.APPROVED)

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    registration = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name='items', verbose_name='Заявка')
    event = models.ForeignKey(Event, on_delete=models.PROTECT, related_name='registration_items', verbose_name='Мероприятие')
    status = models.CharField(max_length=30, choices=Status.choices, verbose_name='Статус')
    decision_note = models.TextField(blank=True, verbose_name='Комментарий к решению')
    decided_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата решения')
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, verbose_name='Решение принял')

    class Meta:
        verbose_name = 'запись на мероприятие'
        verbose_name_plural = 'Записи на мероприятия'
        ordering = ('event__day__position', 'event__start_time', 'event__position')
        constraints = [
            models.UniqueConstraint(fields=('registration', 'event'), name='unique_registration_event'),
        ]

    def __str__(self):
        return f'{self.registration} — {self.event}'


class Lot(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='lots', verbose_name='Мероприятие')
    number = models.PositiveIntegerField(verbose_name='Номер')
    title = models.CharField(max_length=300, verbose_name='Название')
    customer_name = models.CharField(max_length=200, blank=True, verbose_name='Заказчик')
    customer_visible = models.BooleanField(default=False, verbose_name='Показывать заказчика')
    technical_url = models.URLField(verbose_name='Технические материалы')
    position = models.PositiveIntegerField(default=0, verbose_name='Порядок отображения')
    is_published = models.BooleanField(default=False, verbose_name='Показать на сайте')

    class Meta:
        verbose_name = 'лот биржи'
        verbose_name_plural = 'Лоты биржи'
        ordering = ('event', 'position', 'number')
        constraints = [
            models.UniqueConstraint(fields=('event', 'number'), name='unique_lot_number_per_exchange'),
        ]

    def __str__(self):
        return f'Лот {self.number} — {self.title}'

    def clean(self):
        errors = {}
        if self.event_id and self.event.kind != Event.Kind.EXCHANGE:
            errors['event'] = 'Лот можно добавить только к бирже субконтрактов.'
        parsed = urlparse(self.technical_url)
        if parsed.scheme != 'https' or not parsed.netloc:
            errors['technical_url'] = 'Ссылка на технические материалы должна использовать https.'
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class RegistrationItemLot(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    item = models.ForeignKey(RegistrationItem, on_delete=models.CASCADE, related_name='lot_links', verbose_name='Запись на мероприятие')
    lot = models.ForeignKey(Lot, on_delete=models.PROTECT, related_name='registration_links', verbose_name='Лот')

    class Meta:
        verbose_name = 'выбранный лот'
        verbose_name_plural = 'Выбранные лоты'
        constraints = [
            models.UniqueConstraint(fields=('item', 'lot'), name='unique_lot_in_registration_item'),
        ]

    def clean(self):
        if self.item_id and self.lot_id and self.item.event_id != self.lot.event_id:
            raise ValidationError({'lot': 'Лот должен принадлежать событию, на которое подана заявка.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class RegistrationItemHistory(models.Model):
    class ActorKind(models.TextChoices):
        SYSTEM = 'system', 'Система'
        PARTICIPANT = 'participant', 'Участник'
        ADMIN = 'admin', 'Администратор'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    item = models.ForeignKey(RegistrationItem, on_delete=models.CASCADE, related_name='history', verbose_name='Запись на мероприятие')
    action = models.CharField(max_length=40, verbose_name='Действие')
    from_event = models.ForeignKey(Event, on_delete=models.PROTECT, null=True, blank=True, related_name='history_from', verbose_name='Прежнее мероприятие')
    to_event = models.ForeignKey(Event, on_delete=models.PROTECT, null=True, blank=True, related_name='history_to', verbose_name='Новое мероприятие')
    from_status = models.CharField(max_length=30, choices=RegistrationItem.Status.choices, blank=True, verbose_name='Прежний статус')
    to_status = models.CharField(max_length=30, choices=RegistrationItem.Status.choices, verbose_name='Новый статус')
    note = models.TextField(blank=True, verbose_name='Комментарий')
    actor_kind = models.CharField(max_length=20, choices=ActorKind.choices, verbose_name='Кто выполнил')
    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, verbose_name='Сотрудник')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        verbose_name = 'изменение заявки'
        verbose_name_plural = 'История заявок'
        ordering = ('-created_at',)


class Consent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    registration = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name='consents', verbose_name='Заявка')
    document_type = models.CharField(max_length=30, verbose_name='Вид согласия')
    version = models.CharField(max_length=60, verbose_name='Версия')
    text_hash = models.CharField(max_length=64, blank=True, verbose_name='Контрольная сумма текста')
    accepted = models.BooleanField(default=False, verbose_name='Согласие получено')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP-адрес')
    user_agent = models.CharField(max_length=300, blank=True, verbose_name='Браузер')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        verbose_name = 'согласие участника'
        verbose_name_plural = 'Согласия участников'
        ordering = ('registration', 'document_type', '-created_at')


class NotificationOutbox(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = 'pending', 'В очереди'
        SENDING = 'sending', 'Отправляется'
        SENT = 'sent', 'Отправлено'
        FAILED = 'failed', 'Ошибка'
        CANCELLED = 'cancelled', 'Отменено'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    registration = models.ForeignKey(Registration, on_delete=models.CASCADE, related_name='notifications', null=True, blank=True, verbose_name='Заявка')
    kind = models.CharField(max_length=50, choices=[('email_verification', 'Подтверждение почты'), ('registration_summary', 'Подтверждение регистрации'), ('moderation_request', 'Заявка куратору'), ('moderation_decision', 'Решение по заявке'), ('voting_verification', 'Код для голосования'), ('voting_confirmation', 'Подтверждение голосования')], verbose_name='Тип')
    recipient = models.EmailField(verbose_name='Получатель')
    template_version = models.CharField(max_length=60, verbose_name='Версия письма')
    payload = models.JSONField(default=dict, verbose_name='Содержимое письма')
    dedup_key = models.CharField(max_length=200, unique=True, verbose_name='Защита от повторной отправки')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, verbose_name='Статус')
    attempts = models.PositiveIntegerField(default=0, verbose_name='Количество попыток')
    next_attempt_at = models.DateTimeField(default=timezone.now, verbose_name='Следующая попытка')
    locked_at = models.DateTimeField(null=True, blank=True, verbose_name='Начало обработки')
    lock_token = models.UUIDField(null=True, blank=True, verbose_name='Ключ обработки')
    provider_message_id = models.CharField(max_length=255, blank=True, verbose_name='Номер письма у провайдера')
    last_error = models.TextField(blank=True, verbose_name='Последняя ошибка')
    sent_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата отправки')

    class Meta:
        verbose_name = 'письмо'
        verbose_name_plural = 'Письма и уведомления'
        ordering = ('created_at',)

    def __str__(self):
        return f'{self.kind} → {self.recipient} ({self.status})'


class Ticket(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Действует'
        REVOKED = 'revoked', 'Отозван'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    registration = models.OneToOneField(Registration, on_delete=models.CASCADE, related_name='ticket', verbose_name='Заявка')
    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False, verbose_name='Номер билета')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE, verbose_name='Статус')
    version = models.PositiveIntegerField(default=1, verbose_name='Версия')
    issued_at = models.DateTimeField(default=timezone.now, verbose_name='Дата выдачи')
    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата отзыва')

    class Meta:
        verbose_name = 'билет'
        verbose_name_plural = 'Билеты'
        ordering = ('-issued_at',)

    def __str__(self):
        return f'Билет {self.public_id} — {self.registration.participant.full_name}'


class CheckIn(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    ticket = models.ForeignKey(Ticket, on_delete=models.PROTECT, related_name='checkins', verbose_name='Билет')
    admin_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name='Сотрудник регистрации')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        verbose_name = 'отметка прибытия'
        verbose_name_plural = 'Отметки прибытия'
        ordering = ('-created_at',)
        constraints = [
            models.UniqueConstraint(fields=('ticket',), name='unique_general_checkin_per_ticket'),
        ]

    def __str__(self):
        return f'{self.ticket.public_id} — {self.created_at:%d.%m.%Y %H:%M}'


class ExportLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, verbose_name='Сотрудник')
    kind = models.CharField(max_length=40, verbose_name='Тип')
    filters = models.JSONField(default=dict, verbose_name='Параметры выгрузки')
    filename = models.CharField(max_length=200, verbose_name='Имя файла')
    row_count = models.PositiveIntegerField(default=0, verbose_name='Количество строк')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='IP-адрес')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        verbose_name = 'выгрузка'
        verbose_name_plural = 'История выгрузок'
        ordering = ('-created_at',)

    def __str__(self):
        return f'{self.kind} — {self.actor_user.get_username()} — {self.created_at:%d.%m.%Y %H:%M}'


class RegistrationAttemptLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    ip_address = models.GenericIPAddressField(verbose_name='IP-адрес')
    action = models.CharField(max_length=30, verbose_name='Действие')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        verbose_name = 'попытка регистрации'
        verbose_name_plural = 'Попытки регистрации'
        ordering = ('-created_at',)
