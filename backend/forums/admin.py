from django.contrib import admin
from django.utils.html import format_html

from .models import ChoiceGroup, ChoiceGroupEvent, Event, EventDay, EventSpeaker, Forum, RouteEnterprise, Speaker, Venue


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
    raw_id_fields = ('speaker',)
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
    raw_id_fields = ('day', 'venue')
    inlines = (RouteEnterpriseInline, EventSpeakerInline)
    fieldsets = (
        ('Событие', {'fields': ('day', 'venue', 'kind', 'title', 'slug', 'annotation', 'description', 'start_time', 'end_time', 'position', 'is_published')}),
        ('Регистрация', {'fields': ('registration_policy', 'external_url', 'curator_email')}),
        ('Представление', {'fields': ('detail_mode',)}),
        ('Стоимость и вместимость', {'fields': ('is_paid', 'price', 'payment_note', 'capacity_target')}),
        ('Биржа субконтрактов', {'fields': ('min_lot_selections', 'max_lot_selections')}),
    )


class SpeakerEventInline(admin.TabularInline):
    model = EventSpeaker
    extra = 0
    raw_id_fields = ('event',)
    fields = ('event', 'role', 'topic', 'position')


@admin.register(Speaker)
class SpeakerAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'forum', 'topic', 'is_published', 'position')
    list_filter = ('forum', 'is_published')
    search_fields = ('full_name', 'credentials', 'topic')
    raw_id_fields = ('forum',)
    readonly_fields = ('photo_preview',)
    inlines = (SpeakerEventInline,)
    fieldsets = (
        ('Спикер', {'fields': ('forum', 'full_name', 'credentials', 'topic', 'is_published', 'position')}),
        ('Фотография', {'fields': ('photo', 'static_photo', 'photo_preview')}),
    )

    @admin.display(description='Текущая фотография')
    def photo_preview(self, obj):
        if not obj.photo_url:
            return 'Фотография не предоставлена'
        return format_html('<img src="{}" alt="" style="max-width:240px;max-height:280px;object-fit:contain">', obj.photo_url)


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
