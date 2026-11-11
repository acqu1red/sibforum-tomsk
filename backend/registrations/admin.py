from django.contrib import admin, messages
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.core.exceptions import PermissionDenied

from forums.models import Event
from .models import (
    CheckIn,
    Consent,
    ExportLog,
    Lot,
    NotificationOutbox,
    Participant,
    Registration,
    RegistrationItem,
    RegistrationItemHistory,
    RegistrationItemLot,
    Ticket,
)
from .selection import RegistrationError
from .workflow import decide_item


@admin.register(Lot)
class LotAdmin(admin.ModelAdmin):
    list_display = ('number', 'title', 'event', 'customer_visible', 'is_published', 'position')
    list_filter = ('event__day__forum', 'is_published', 'customer_visible')
    search_fields = ('title', 'customer_name', 'event__title')
    raw_id_fields = ('event',)


class ConsentInline(admin.TabularInline):
    model = Consent
    extra = 0
    can_delete = False
    readonly_fields = ('document_type', 'version', 'accepted', 'ip_address', 'user_agent', 'created_at')

    def has_add_permission(self, request, obj=None):
        return False


class RegistrationItemInline(admin.TabularInline):
    model = RegistrationItem
    extra = 0
    fields = ('event', 'status', 'decided_at', 'decided_by')
    readonly_fields = ('event', 'status', 'decided_at', 'decided_by')
    show_change_link = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Registration)
class RegistrationAdmin(admin.ModelAdmin):
    list_display = ('participant', 'forum', 'email_verified_at', 'version', 'created_at')
    list_filter = ('participant__forum', 'email_verified_at')
    search_fields = ('participant__last_name', 'participant__first_name', 'participant__email', 'participant__organization')
    readonly_fields = ('participant', 'email_verified_at', 'token_issued_at', 'version', 'created_at', 'updated_at')
    exclude = ('access_token_hash',)
    inlines = (RegistrationItemInline, ConsentInline)

    def has_add_permission(self, request):
        return False

    @admin.display(ordering='participant__forum', description='Форум')
    def forum(self, obj):
        return obj.participant.forum


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ('participant_full_name', 'forum', 'email', 'organization', 'position')
    list_filter = ('forum', 'category')
    search_fields = ('last_name', 'first_name', 'middle_name', 'email', 'organization')
    readonly_fields = ('created_at', 'updated_at')

    @admin.display(description='Участник', ordering='last_name')
    def participant_full_name(self, obj):
        return obj.full_name


class RegistrationItemLotInline(admin.TabularInline):
    model = RegistrationItemLot
    extra = 0
    readonly_fields = ('lot',)

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(RegistrationItem)
class RegistrationItemAdmin(admin.ModelAdmin):
    list_display = ('participant_name', 'event', 'status', 'decided_at', 'decided_by')
    list_filter = ('status', 'event__day__forum', 'event__kind')
    search_fields = ('registration__participant__last_name', 'registration__participant__email', 'event__title')
    readonly_fields = ('registration', 'event', 'status', 'decided_at', 'decided_by', 'created_at', 'updated_at')
    inlines = (RegistrationItemLotInline,)
    actions = ('approve_selected', 'reject_selected', 'cancel_selected', 'move_selected')

    def has_add_permission(self, request):
        return False

    def change_view(self, request, object_id, form_url='', extra_context=None):
        action = request.POST.get('_moderation_action') if request.method == 'POST' else None
        if action in ('approve', 'reject', 'cancel'):
            item = self.get_object(request, object_id)
            if not item or not self.has_change_permission(request, item):
                raise PermissionDenied
            try:
                decide_item(item.pk, action, request.user, note=request.POST.get('decision_note', ''))
            except RegistrationError as error:
                self.message_user(request, error.message, level=messages.ERROR)
            else:
                self.log_change(request, item, 'Решение по заявке принято через карточку.')
                self.message_user(request, 'Решение сохранено. Уведомление участнику поставлено в очередь.')
            return redirect(request.path)
        return super().change_view(request, object_id, form_url, extra_context)

    @admin.display(ordering='registration__participant__last_name', description='Участник')
    def participant_name(self, obj):
        return obj.registration.participant.full_name

    def move_form(self, request, item, note=''):
        routes = Event.objects.filter(
            day__forum=item.event.day.forum,
            kind=Event.Kind.ROUTE,
            registration_policy=Event.RegistrationPolicy.MODERATED,
            is_published=True,
        ).exclude(id=item.event_id).order_by('day__position', 'position')
        context = self.admin_site.each_context(request)
        context.update({
            'title': 'Перевод участника на другой маршрут',
            'item': item,
            'routes': routes,
            'selected_ids': [str(item.id)],
            'action_checkbox_name': '_selected_action',
            'note': note,
        })
        return TemplateResponse(request, 'registrations/move_route.html', context)

    @admin.action(description='Перевести выбранную заявку на другой маршрут')
    def move_selected(self, request, queryset):
        if queryset.count() != 1:
            self.message_user(request, 'Выберите ровно одну заявку для перевода.', level=messages.ERROR)
            return redirect('admin:registrations_registrationitem_changelist')
        item = queryset.select_related('registration__participant', 'event__day__forum').first()
        if request.POST.get('confirm') == '1':
            note = str(request.POST.get('note') or '').strip()
            try:
                decide_item(item.id, 'move', request.user, note=note or 'Перевод через админку', target_event_id=request.POST.get('target_event'))
            except RegistrationError as error:
                self.message_user(request, error.message, level=messages.ERROR)
            else:
                self.message_user(request, 'Участник переведён на новый маршрут, уведомление поставлено в очередь.', level=messages.SUCCESS)
                return redirect('admin:registrations_registrationitem_changelist')
        return self.move_form(request, item, note=request.POST.get('note', ''))

    def run_action(self, request, queryset, action, label):
        count = 0
        for item in queryset:
            try:
                decide_item(item.id, action, request.user, note=label)
                count += 1
            except RegistrationError as error:
                self.message_user(request, f'{item}: {error.message}', level=messages.ERROR)
        if count:
            self.message_user(request, f'Обработано заявок: {count}.', level=messages.SUCCESS)

    @admin.action(description='Одобрить выбранные заявки')
    def approve_selected(self, request, queryset):
        self.run_action(request, queryset, 'approve', 'Одобрено администратором')

    @admin.action(description='Отклонить выбранные заявки')
    def reject_selected(self, request, queryset):
        self.run_action(request, queryset, 'reject', 'Отклонено администратором')

    @admin.action(description='Отменить выбранные заявки')
    def cancel_selected(self, request, queryset):
        self.run_action(request, queryset, 'cancel', 'Отменено администратором')


@admin.register(RegistrationItemHistory)
class RegistrationItemHistoryAdmin(admin.ModelAdmin):
    list_display = ('item', 'action', 'from_status', 'to_status', 'actor_kind', 'actor_user', 'created_at')
    list_filter = ('action', 'actor_kind', 'created_at')
    readonly_fields = ('item', 'action', 'from_event', 'to_event', 'from_status', 'to_status', 'note', 'actor_kind', 'actor_user', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(NotificationOutbox)
class NotificationOutboxAdmin(admin.ModelAdmin):
    list_display = ('kind', 'recipient', 'status', 'attempts', 'next_attempt_at', 'sent_at')
    list_filter = ('kind', 'status', 'created_at')
    search_fields = ('recipient', 'dedup_key')
    readonly_fields = ('registration', 'kind', 'recipient', 'template_version', 'dedup_key', 'attempts', 'locked_at', 'lock_token', 'provider_message_id', 'last_error', 'sent_at', 'created_at', 'updated_at')
    exclude = ('payload',)
    actions = ('retry_failed',)

    def has_add_permission(self, request):
        return False

    @admin.action(description='Вернуть ошибочные письма в очередь')
    def retry_failed(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status=NotificationOutbox.Status.FAILED).update(
            status=NotificationOutbox.Status.PENDING,
            next_attempt_at=timezone.now(),
            locked_at=None,
            lock_token=None,
            last_error='',
        )
        self.message_user(request, f'Писем возвращено в очередь: {updated}.')


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('public_id', 'registration', 'status', 'version', 'issued_at', 'revoked_at')
    list_filter = ('status', 'issued_at')
    search_fields = ('public_id', 'registration__participant__last_name', 'registration__participant__email')
    readonly_fields = ('registration', 'public_id', 'status', 'version', 'issued_at', 'revoked_at', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        return False


@admin.register(CheckIn)
class CheckInAdmin(admin.ModelAdmin):
    list_display = ('ticket', 'admin_user', 'created_at')
    list_filter = ('created_at', 'admin_user')
    search_fields = ('ticket__public_id', 'ticket__registration__participant__last_name')
    readonly_fields = ('ticket', 'admin_user', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ExportLog)
class ExportLogAdmin(admin.ModelAdmin):
    list_display = ('kind', 'actor_user', 'filename', 'row_count', 'ip_address', 'created_at')
    list_filter = ('kind', 'actor_user', 'created_at')
    search_fields = ('filename', 'actor_user__username')
    readonly_fields = ('actor_user', 'kind', 'filters', 'filename', 'row_count', 'ip_address', 'created_at')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
