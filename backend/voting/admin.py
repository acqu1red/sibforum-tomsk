from django.contrib import admin

from .models import Contest, Nomination, Nominee


class NominationInline(admin.TabularInline):
    model = Nomination
    extra = 0
    fields = ('title', 'description', 'visual_group', 'min_selections', 'max_selections', 'position', 'is_active')
    show_change_link = True


@admin.register(Contest)
class ContestAdmin(admin.ModelAdmin):
    list_display = ('title', 'forum', 'is_open', 'voting_opens_at', 'voting_closes_at', 'results_published')
    list_filter = ('is_open', 'results_published', 'forum')
    search_fields = ('title', 'forum__title')
    inlines = (NominationInline,)
    actions = ('close_voting', 'publish_results')

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
    fields = ('name', 'description', 'website_url', 'position', 'is_active')


@admin.register(Nomination)
class NominationAdmin(admin.ModelAdmin):
    list_display = ('title', 'contest', 'visual_group', 'min_selections', 'max_selections', 'position', 'is_active')
    list_filter = ('contest', 'visual_group', 'is_active')
    search_fields = ('title', 'nominees__name')
    inlines = (NomineeInline,)
