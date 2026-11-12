from django.contrib import admin
from django.utils.html import format_html

from .models import ContactCard, ForumPage, InterfaceText, NavigationItem, OrganizationLogo, PageSection, SpeakerPhoto


class WebsiteAdmin(admin.ModelAdmin):
    autocomplete_fields = ('forum',)
    list_filter = ('forum',)
    save_on_top = True

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        from .models import Forum
        forum = Forum.objects.filter(slug='promtour').first()
        if forum:
            initial.setdefault('forum', forum.pk)
        return initial


@admin.register(InterfaceText)
class InterfaceTextAdmin(WebsiteAdmin):
    list_display = ('get_key_display', 'value', 'forum')
    search_fields = ('value', 'key')
    fields = ('forum', 'key', 'value')


@admin.register(ForumPage)
class ForumPageAdmin(WebsiteAdmin):
    list_display = ('forum', 'brand_name', 'updated_at')
    autocomplete_fields = ('forum', 'main_venue')
    fieldsets = (
        ('Страница и шапка', {'fields': ('forum', 'brand_name', 'brand_subtitle', 'brand_logo', 'brand_static_logo', 'date_label')}),
        ('Первый экран', {'fields': ('main_venue', 'venue_label', 'venue_note', 'hero_image', 'hero_static_image')}),
        ('Организатор и регистрация', {'fields': ('organizer_email', 'registration_notice', 'footer_text')}),
    )


@admin.register(PageSection)
class PageSectionAdmin(WebsiteAdmin):
    list_display = ('get_key_display', 'heading', 'forum', 'is_published', 'updated_at')
    list_editable = ('is_published',)
    search_fields = ('heading', 'body')
    fieldsets = (
        ('Раздел', {'fields': ('forum', 'key', 'is_published')}),
        ('Тексты', {'fields': ('heading', 'eyebrow', 'body', 'note'), 'description': 'Текст публикуется как обычный текст. Для переноса строки нажмите Enter. Разметка HTML не нужна.'}),
        ('Кнопка раздела', {'fields': ('action_label', 'action_url')}),
    )

    def get_fieldsets(self, request, obj=None):
        if obj and obj.key == 'contest':
            return (
                ('Раздел конкурса', {'fields': ('forum', 'key', 'is_published'), 'description': 'Название и описание меняются в разделе «Конкурсы» и автоматически используются на обеих страницах.'}),
                ('Пояснения', {'fields': ('eyebrow', 'note')}),
                ('Кнопка', {'fields': ('action_label', 'action_url')}),
            )
        return super().get_fieldsets(request, obj)


@admin.register(NavigationItem)
class NavigationItemAdmin(WebsiteAdmin):
    list_display = ('label', 'target', 'forum', 'position', 'is_published')
    list_editable = ('position', 'is_published')
    search_fields = ('label',)


@admin.register(ContactCard)
class ContactCardAdmin(WebsiteAdmin):
    list_display = ('contact_name', 'subtitle', 'forum', 'position', 'is_published')
    list_editable = ('position', 'is_published')
    search_fields = ('title', 'body')
    autocomplete_fields = ('forum', 'venue')

    @admin.display(description='Контакт')
    def contact_name(self, obj):
        return str(obj)


@admin.register(OrganizationLogo)
class OrganizationLogoAdmin(WebsiteAdmin):
    list_display = ('name', 'group', 'forum', 'preview', 'position', 'is_published')
    list_editable = ('position', 'is_published')
    list_filter = ('forum', 'group', 'is_published')
    search_fields = ('name',)
    readonly_fields = ('preview',)
    fields = ('forum', 'group', 'route_enterprise', 'name', 'image', 'static_image', 'image_background', 'preview', 'website_url', 'position', 'is_published')

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == 'route_enterprise':
            from .models import RouteEnterprise
            kwargs['queryset'] = RouteEnterprise.objects.filter(event__day__forum__slug='promtour', event__kind='route')
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.display(description='Логотип')
    def preview(self, obj):
        from .media import public_asset
        url = obj.variants.get('400') or (obj.image.url if obj.image else public_asset(obj.static_image, absolute=True))
        return format_html('<img src="{}" alt="" style="width:120px;height:64px;object-fit:contain;background:{};padding:8px;border-radius:8px">', url, '#071466' if obj.image_background == 'dark' else '#fff') if url else 'Логотип ещё не загружен'


class SpeakerPhotoInline(admin.StackedInline):
    model = SpeakerPhoto
    extra = 4
    max_num = 4
    fields = ('placement', 'image', ('fit', 'focal_x', 'focal_y'))
    verbose_name_plural = 'Отдельные варианты и кадрирование — оставьте файл пустым, чтобы использовать общую фотографию'

    def get_formset(self, request, obj=None, **kwargs):
        base = super().get_formset(request, obj, **kwargs)
        class PlacementFormSet(base):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                existing = set(self.queryset.values_list('placement', flat=True))
                missing = [key for key, label in SpeakerPhoto.PLACEMENTS if key not in existing]
                for form, key in zip(self.extra_forms, missing):
                    form.initial.update(placement=key, fit='contain' if key == 'dialog' else 'cover')
        return PlacementFormSet
