from django.contrib import admin
from django.utils.html import format_html

from .models import ChoiceGroup, ChoiceGroupEvent, Event, EventDay, EventSpeaker, Forum, RouteEnterprise, Speaker, Venue
from .content_admin import SpeakerPhotoInline
from .content import speaker_photos
from .media import public_asset
from django.utils.html import format_html_join


class VenueInline(admin.TabularInline):
    model = Venue
    extra = 0
    fields = ('name', 'address', 'map_url', 'position', 'is_published')


class EventDayInline(admin.TabularInline):
    model = EventDay
    extra = 0
    fields = ('date', 'title', 'position')
    show_change_link = True


@admin.register(Forum)
class ForumAdmin(admin.ModelAdmin):
    list_display = ('title', 'series', 'starts_at', 'ends_at', 'status', 'is_featured')
    list_filter = ('series', 'status', 'is_featured')
    search_fields = ('title', 'short_title', 'slug')
    prepopulated_fields = {'slug': ('short_title',)}
    inlines = (VenueInline, EventDayInline)


class EventInline(admin.TabularInline):
    model = Event
    extra = 0
    fields = ('title', 'kind', 'start_time', 'end_time', 'registration_policy', 'position', 'is_published')
    show_change_link = True


class ChoiceGroupInline(admin.TabularInline):
    model = ChoiceGroup
    extra = 0
    fields = ('title', 'min_selections', 'max_selections', 'position')
    show_change_link = True


@admin.register(EventDay)
class EventDayAdmin(admin.ModelAdmin):
    list_display = ('date', 'title', 'forum', 'position')
    list_filter = ('forum', 'date')
    search_fields = ('title', 'forum__title')
    inlines = (EventInline, ChoiceGroupInline)


@admin.register(Venue)
class VenueAdmin(admin.ModelAdmin):
    list_display = ('name', 'forum', 'position', 'is_published')
    list_filter = ('forum', 'is_published')
    search_fields = ('name', 'address', 'forum__title')


class EventSpeakerInline(admin.TabularInline):
    model = EventSpeaker
    extra = 0
    autocomplete_fields = ('speaker',)
    fields = ('speaker', 'role', 'topic', 'position')


class RouteEnterpriseInline(admin.TabularInline):
    model = RouteEnterprise
    extra = 0
    fields = ('name', 'description', 'position')


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('title', 'day', 'start_time', 'end_time', 'kind', 'registration_policy', 'is_paid', 'is_published')
    list_filter = ('day__forum', 'kind', 'registration_policy', 'is_paid', 'is_published')
    search_fields = ('title', 'annotation', 'description', 'day__forum__title')
    autocomplete_fields = ('day', 'venue')
    inlines = (RouteEnterpriseInline, EventSpeakerInline)

    def get_list_display(self, request):
        if request.GET.get('kind__exact') == Event.Kind.ROUTE:
            return ('title', 'day', 'contact_name', 'contact_phone', 'is_published')
        return super().get_list_display(request)

    fieldsets = (
        ('Событие', {'fields': ('day', 'venue', 'kind', 'title', 'slug', 'annotation', 'description', 'start_time', 'end_time', 'position', 'is_published')}),
        ('Регистрация', {'fields': ('registration_policy', 'external_url', 'curator_email')}),
        ('Контакт для посетителей', {'fields': ('contact_name', 'contact_phone'), 'description': 'Показывается в карточке маршрута и при выборе мероприятия. Пустые поля не выводятся.'}),
        ('Представление', {'fields': ('detail_mode',)}),
        ('Стоимость и вместимость', {'fields': ('is_paid', 'price', 'payment_note', 'capacity_target')}),
        ('Биржа субконтрактов', {'fields': ('min_lot_selections', 'max_lot_selections')}),
    )


class SpeakerEventInline(admin.TabularInline):
    model = EventSpeaker
    extra = 0
    autocomplete_fields = ('event',)
    fields = ('event', 'role', 'topic', 'position')


@admin.register(Speaker)
class SpeakerAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'forum', 'topic', 'is_published', 'position')
    list_filter = ('forum', 'is_published')
    search_fields = ('full_name', 'credentials', 'topic')
    autocomplete_fields = ('forum',)
    readonly_fields = ('photo_preview',)
    inlines = (SpeakerPhotoInline, SpeakerEventInline)
    fieldsets = (
        ('Спикер', {'fields': ('forum', 'full_name', 'short_name', 'short_position', 'credentials', 'topic', 'is_published', 'position')}),
        ('Общая фотография и предпросмотр', {'fields': ('photo', 'static_photo', 'photo_preview'), 'description': 'Загрузите одну фотографию для всех мест. Если в каком-то месте кадр не подходит, задайте отдельный вариант ниже. Предпросмотр обновится сразу, ещё до сохранения.'}),
    )

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        forum = Forum.objects.filter(slug='promtour').first()
        if forum:
            initial.setdefault('forum', forum.pk)
        return initial

    @admin.display(description='Текущая фотография')
    def photo_preview(self, obj):
        photos = speaker_photos(obj) if obj.pk and obj._state.adding is False else {}
        cards = []
        for key, title in SpeakerPhotoInline.model.PLACEMENTS:
            photo = photos.get(key, {})
            cards.append((key, title, public_asset(photo.get('url', ''), absolute=True), public_asset(photo.get('url', ''), absolute=True), photo.get('fit', 'contain' if key == 'dialog' else 'cover'), photo.get('x', 50), photo.get('y', 25), obj.display_name if obj.full_name else 'Имя спикера', obj.short_position))
        return format_html('<div class="speaker-preview" data-speaker-preview data-base-url="{}">{}</div>', public_asset(obj.photo_url, absolute=True), format_html_join('', '<figure data-photo-context="{}"><figcaption>{}</figcaption><div class="speaker-preview-frame"><img src="{}" data-original="{}" data-fit="{}" data-x="{}" data-y="{}" alt="Предпросмотр"><span>Нет фотографии</span></div><b data-preview-name>{}</b><small data-preview-position>{}</small></figure>', cards))

    class Media:
        css = {'all': ('workspace/content-editor.css',)}
        js = ('workspace/speaker-preview.js',)


class ChoiceGroupEventInline(admin.TabularInline):
    model = ChoiceGroupEvent
    extra = 0
    raw_id_fields = ('event',)
    fields = ('event', 'position')


@admin.register(ChoiceGroup)
class ChoiceGroupAdmin(admin.ModelAdmin):
    list_display = ('title', 'day', 'min_selections', 'max_selections', 'position')
    list_filter = ('day__forum',)
    search_fields = ('title', 'day__title', 'day__forum__title')
    raw_id_fields = ('day',)
    inlines = (ChoiceGroupEventInline,)
