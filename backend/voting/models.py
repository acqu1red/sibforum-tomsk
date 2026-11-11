import uuid

from django.conf import settings
from django.db import models

from forums.models import Forum, TimeStampedModel


class Contest(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    forum = models.OneToOneField(Forum, on_delete=models.CASCADE, related_name='contest', verbose_name='Форум')
    title = models.CharField(max_length=240, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    rules_text = models.TextField(blank=True, verbose_name='Правила конкурса')
    is_open = models.BooleanField(default=False, verbose_name='Голосование разрешено')
    voting_opens_at = models.DateTimeField(null=True, blank=True, verbose_name='Начало голосования')
    voting_closes_at = models.DateTimeField(null=True, blank=True, verbose_name='Окончание голосования')
    results_published = models.BooleanField(default=False, verbose_name='Итоги опубликованы')
    winners_text = models.TextField(blank=True, verbose_name='Текст итогов')

    class Meta:
        verbose_name = 'конкурс'
        verbose_name_plural = 'Конкурсы'

    def __str__(self):
        return f'{self.title} — {self.forum}'


class Nomination(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE, related_name='nominations', verbose_name='Конкурс')
    title = models.CharField(max_length=300, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    visual_group = models.PositiveSmallIntegerField(default=0, verbose_name='Группа на странице')
    min_selections = models.PositiveSmallIntegerField(default=0, verbose_name='Минимум вариантов')
    max_selections = models.PositiveSmallIntegerField(default=1, verbose_name='Максимум вариантов')
    position = models.PositiveSmallIntegerField(default=0, verbose_name='Порядок отображения')
    is_active = models.BooleanField(default=True, verbose_name='Активно')

    class Meta:
        verbose_name = 'номинация'
        verbose_name_plural = 'Номинации'
        ordering = ('contest', 'position', 'title')
        constraints = [
            models.UniqueConstraint(fields=('contest', 'title'), name='unique_nomination_title_per_contest'),
            models.CheckConstraint(condition=models.Q(max_selections__gte=models.F('min_selections')), name='nomination_limits_valid'),
        ]

    def __str__(self):
        return self.title


class Nominee(TimeStampedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    nomination = models.ForeignKey(Nomination, on_delete=models.CASCADE, related_name='nominees', verbose_name='Номинация')
    name = models.CharField(max_length=500, verbose_name='Название')
    description = models.TextField(blank=True, verbose_name='Описание')
    website_url = models.URLField(blank=True, verbose_name='Сайт проекта')
    position = models.PositiveIntegerField(default=0, verbose_name='Порядок отображения')
    is_active = models.BooleanField(default=True, verbose_name='Активно')

    class Meta:
        verbose_name = 'кандидат'
        verbose_name_plural = 'Кандидаты'
        ordering = ('nomination', 'position', 'name')
        constraints = [
            models.UniqueConstraint(fields=('nomination', 'name'), name='unique_nominee_name_per_nomination'),
        ]

    def __str__(self):
        return self.name


class Ballot(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING_EMAIL = 'pending_email', 'Ожидает подтверждения email'
        SUBMITTED = 'submitted', 'Принят'
        CANCELLED = 'cancelled', 'Отменён'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE, related_name='ballots', verbose_name='Конкурс')
    email = models.EmailField(verbose_name='Электронная почта')
    identity_hash = models.CharField(max_length=64, verbose_name='Защита от повторного голосования')
    code_hash = models.CharField(max_length=256, verbose_name='Защищённый код подтверждения')
    pending_selection = models.JSONField(default=list, verbose_name='Выбор до подтверждения')
    verification_expires_at = models.DateTimeField(verbose_name='Код действует до')
    verification_attempts = models.PositiveSmallIntegerField(default=0, verbose_name='Попыток подтверждения')
    email_verified_at = models.DateTimeField(null=True, blank=True, verbose_name='Почта подтверждена')
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name='Дата голосования')
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING_EMAIL, verbose_name='Статус')

    class Meta:
        verbose_name = 'бюллетень'
        verbose_name_plural = 'Бюллетени'
        ordering = ('-created_at',)
        constraints = [
            models.UniqueConstraint(fields=('contest', 'email'), name='unique_email_ballot_per_contest'),
        ]

    def __str__(self):
        return f'Бюллетень {self.id} — {self.contest}'


class VoteSelection(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    ballot = models.ForeignKey(Ballot, on_delete=models.CASCADE, related_name='selections', verbose_name='Бюллетень')
    nomination = models.ForeignKey(Nomination, on_delete=models.PROTECT, verbose_name='Номинация')
    nominee = models.ForeignKey(Nominee, on_delete=models.PROTECT, verbose_name='Кандидат')

    class Meta:
        verbose_name = 'голос'
        verbose_name_plural = 'Голоса'
        constraints = [
            models.UniqueConstraint(fields=('ballot', 'nomination', 'nominee'), name='unique_vote_per_nominee_per_ballot'),
        ]


class VoteAttemptLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, verbose_name='Идентификатор')
    ip_address = models.GenericIPAddressField(verbose_name='IP-адрес')
    action = models.CharField(max_length=30, verbose_name='Действие')
    success = models.BooleanField(default=True, verbose_name='Успешно')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Дата создания')

    class Meta:
        verbose_name = 'попытка голосования'
        verbose_name_plural = 'Попытки голосования'
        ordering = ('-created_at',)
