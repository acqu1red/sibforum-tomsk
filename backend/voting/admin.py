from django.contrib import admin
from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.template.response import TemplateResponse
from django.utils.html import format_html, format_html_join

from .models import Ballot, Contest, Nomination, Nominee, NomineePhoto, VoteResetLog
from .simple import reset_ballots
from .workflow import stats_payload


class NominationInline(admin.TabularInline):
    model = Nomination
    extra = 0
    fields = ('title', 'max_selections', 'selection_hint', 'position', 'is_active')
    show_change_link = True


@admin.register(Contest)
class ContestAdmin(admin.ModelAdmin):
    list_display = ('title', 'forum', 'is_open', 'voting_opens_at', 'voting_closes_at', 'results_published')
    list_filter = ('is_open', 'results_published', 'forum')
    search_fields = ('title', 'forum__title')
    inlines = (NominationInline,)
    actions = ('close_voting', 'publish_results')
    autocomplete_fields = ('forum',)
    readonly_fields = ('results_preview',)
    fieldsets = (
        ('О конкурсе', {'fields': ('forum', 'title', 'description', 'rules_text')}),
        ('Голосование', {'fields': ('is_open', 'voting_mode', 'max_ballots_per_network', 'voting_opens_at', 'voting_closes_at'), 'description': 'Время задаётся по Томску. Без почты посетитель голосует сразу; с почтой нужен настроенный SMTP. Ограничение сети учитывает общий IP офиса и Wi-Fi.'}),
        ('Итоги', {'fields': ('results_published', 'winners_text', 'results_preview')}),
    )

    @admin.display(description='Принятые голоса')
    def results_preview(self, obj):
        if not obj.pk:
            return 'Сначала сохраните конкурс.'
        stats = stats_payload(obj)
        rows = [(n['title'], person['name'], person['votes']) for n in stats['nominations'] for person in n['nominees']]
        return format_html('<p>Принято бюллетеней: <strong>{}</strong></p><p><a href="/admin/voting/ballot/?contest__id__exact={}">Открыть бюллетени и сброс тестовых голосов</a></p><table><thead><tr><th>Номинация</th><th>Участник</th><th>Голоса</th></tr></thead><tbody>{}</tbody></table>', stats['total_ballots'], obj.pk, format_html_join('', '<tr><td>{}</td><td>{}</td><td>{}</td></tr>', rows))

    @admin.action(description='Закрыть голосование')
    def close_voting(self, request, queryset):
        updated = queryset.update(is_open=False)
        self.message_user(request, f'Закрыто конкурсов: {updated}.')

    @admin.action(description='Опубликовать итоги и закрыть голосование')
    def publish_results(self, request, queryset):
        updated = queryset.update(is_open=False, results_published=True)
        self.message_user(request, f'Итоги опубликованы: {updated}.')


class NomineeInline(admin.TabularInline):
    model = Nominee
    extra = 0
    fields = ('name', 'logo', 'website_url', 'position', 'is_active')
    show_change_link = True


@admin.register(Nomination)
class NominationAdmin(admin.ModelAdmin):
    list_display = ('title', 'contest', 'visual_group', 'min_selections', 'max_selections', 'position', 'is_active')
    list_filter = ('contest', 'visual_group', 'is_active')
    search_fields = ('title', 'nominees__name')
    inlines = (NomineeInline,)
    autocomplete_fields = ('contest',)
    fieldsets = (
        ('Номинация', {'fields': ('contest', 'title', 'description', 'position', 'is_active')}),
        ('Выбор посетителя', {'fields': ('min_selections', 'max_selections', 'selection_hint'), 'description': 'Обычно минимум 0: посетитель может голосовать только в знакомых номинациях. Максимум определяет реальный лимит, а не только надпись.'}),
    )


class NomineePhotoInline(admin.TabularInline):
    verbose_name_plural = 'Фотографии в окне «Описание»'
    model = NomineePhoto
    extra = 1
    fields = ('image', 'caption', 'position')


@admin.register(Nominee)
class NomineeAdmin(admin.ModelAdmin):
    list_display = ('name', 'nomination', 'position', 'is_active')
    list_filter = ('nomination__contest', 'nomination', 'is_active')
    search_fields = ('name', 'description')
    autocomplete_fields = ('nomination',)
    inlines = (NomineePhotoInline,)
    fieldsets = (
        ('Компания в номинации', {'fields': ('nomination', 'name', 'position', 'is_active')}),
        ('Логотип в списке компаний', {'fields': ('logo', 'static_logo')}),
        ('Окно «Описание»', {'fields': ('description', 'website_url'), 'description': 'Фотографии добавьте ниже, в блоке «Фотографии в окне Описание». Они относятся к этой компании в выбранной номинации.'}),
    )
    save_on_top = True


def is_owner(request):
    return request.user.is_active and request.user.is_superuser and request.user.get_username() == settings.ADMIN_OWNER_USERNAME


@admin.register(Ballot)
class BallotAdmin(admin.ModelAdmin):
    list_display = ('id', 'contest', 'submitted_at', 'status')
    list_filter = ('contest', 'status')
    search_fields = ('id', 'email')
    readonly_fields = ('id', 'contest', 'email', 'status', 'submitted_at', 'created_at', 'selection_preview')
    fields = readonly_fields
    actions = ('reset_test_ballots',)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_reset_permission(self, request):
        return is_owner(request)

    @admin.display(description='Выбор в бюллетене')
    def selection_preview(self, obj):
        return format_html('<ul>{}</ul>', format_html_join('', '<li>{} — {}</li>', ((s.nomination.title, s.nominee.name) for s in obj.selections.select_related('nomination', 'nominee'))))

    @admin.action(description='Сбросить выбранные тестовые бюллетени…', permissions=['reset'])
    def reset_test_ballots(self, request, queryset):
        if not is_owner(request):
            raise PermissionDenied
        error = ''
        if request.POST.get('confirm_reset'):
            reason = request.POST.get('reason', '').strip()
            if request.POST.get('confirmation') != 'СБРОСИТЬ' or not reason:
                error = 'Укажите причину и введите слово СБРОСИТЬ.'
            else:
                count = 0
                for contest in Contest.objects.filter(ballots__in=queryset).distinct():
                    count += reset_ballots(contest=contest, ballots=queryset, actor=request.user, reason=reason)
                self.message_user(request, f'Отменено тестовых бюллетеней: {count}. Остальные голоса сохранены.')
                return None
        return TemplateResponse(request, 'admin/voting/reset_votes.html', {**self.admin_site.each_context(request), 'title': 'Сброс тестовых голосов', 'queryset': queryset, 'opts': self.model._meta, 'error': error, 'select_across': request.POST.get('select_across', '0')})


@admin.register(VoteResetLog)
class VoteResetLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'contest', 'actor', 'reason')
    readonly_fields = ('created_at', 'contest', 'actor', 'reason', 'ballot_ids')
    fields = readonly_fields

    def has_module_permission(self, request):
        return is_owner(request)

    def has_view_permission(self, request, obj=None):
        return is_owner(request)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
