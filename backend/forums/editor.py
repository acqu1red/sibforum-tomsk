"""Staff-only visual editing of the same catalog used by the public site."""
import re
from hashlib import sha256
from pathlib import Path

from django import forms
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.models import ADDITION, CHANGE, DELETION, LogEntry
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.forms import inlineformset_factory, modelform_factory
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template.loader import render_to_string
from django.urls import path, reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_GET, require_http_methods

from registrations.models import Lot
from voting.models import Contest, Nomination, Nominee, NomineePhoto
from .content import speaker_photos
from .media import public_asset
from .models import (ContactCard, Event, EventDay, EventSpeaker, Forum, ForumPage,
                     InterfaceText, NavigationItem, OrganizationLogo, PageSection, RouteEnterprise,
                     Speaker, SpeakerPhoto, Venue)

# Explicit fields keep account privileges, IDs and technical flags out of writes.
SPECS = {
 'page': (ForumPage, 'forum', 'Шапка и первый экран', ['brand_name', 'brand_subtitle', 'brand_logo', 'date_label', 'hero_image', 'main_venue', 'venue_label', 'venue_note', 'organizer_email', 'footer_text', 'registration_notice']),
 'section': (PageSection, 'forum', 'Тексты разделов', ['heading', 'eyebrow', 'body', 'note', 'action_label', 'action_url', 'is_published']),
 'interface': (InterfaceText, 'forum', 'Подписи и пояснения', ['value']),
 'speaker': (Speaker, 'forum', 'Спикеры', ['full_name', 'short_name', 'short_position', 'credentials', 'topic', 'photo', 'position', 'is_published']),
 'event': (Event, 'day__forum', 'Программа и маршруты', ['title', 'day', 'start_time', 'end_time', 'venue', 'annotation', 'description', 'contact_name', 'contact_phone', 'is_published', 'position', 'registration_policy', 'external_url', 'is_paid', 'price', 'payment_note', 'capacity_target', 'curator_email', 'min_lot_selections', 'max_lot_selections', 'detail_mode']),
 'day': (EventDay, 'forum', 'Дни программы', ['title', 'date', 'position']),
 'venue': (Venue, 'forum', 'Площадки', ['name', 'address', 'map_url', 'position', 'is_published']),
 'contact': (ContactCard, 'forum', 'Контакты', ['title', 'venue', 'subtitle', 'body', 'link_label', 'link_url', 'position', 'is_published']),
 'logo': (OrganizationLogo, 'forum', 'Организаторы, партнёры и промтуризм', ['group', 'route_enterprise', 'name', 'image', 'image_background', 'website_url', 'position', 'is_published']),
 'menu': (NavigationItem, 'forum', 'Верхнее меню', ['label', 'target', 'position', 'is_published']),
 'contest': (Contest, 'forum', 'Конкурс и голосование', ['title', 'description', 'rules_text', 'voting_mode', 'max_ballots_per_network', 'is_open', 'voting_opens_at', 'voting_closes_at', 'results_published', 'winners_text']),
 'nomination': (Nomination, 'contest__forum', 'Номинации', ['title', 'description', 'selection_hint', 'min_selections', 'max_selections', 'position', 'is_active']),
 'nominee': (Nominee, 'nomination__contest__forum', 'Компании в конкурсе', ['nomination', 'name', 'description', 'logo', 'website_url', 'position', 'is_active']),
 'lot': (Lot, 'event__day__forum', 'Лоты биржи', ['event', 'number', 'title', 'customer_name', 'customer_visible', 'technical_url', 'is_published', 'position']),
}


def current_forum():
    return get_object_or_404(Forum, slug='promtour')


def queryset(kind, forum):
    model, lookup, _, _ = SPECS[kind]
    return model.objects.filter(**{lookup: forum})


def can(user, kind, action='change'):
    model = SPECS[kind][0]
    return user.has_perm(f'{model._meta.app_label}.{action}_{model._meta.model_name}')


def label(obj):
    if isinstance(obj, PageSection):
        return obj.get_key_display()
    return str(obj)


def catalog(user, forum):
    groups = []
    for kind, (model, _, title, _) in SPECS.items():
        if not can(user, kind):
            continue
        items = []
        for obj in queryset(kind, forum):
            item = {'kind': kind, 'id': str(obj.pk), 'label': label(obj),
                    'key': getattr(obj, 'key', '') or getattr(obj, 'slug', ''),
                    'image': '', 'group': getattr(obj, 'group', '')}
            if isinstance(obj, Speaker):
                item['image'] = public_asset(obj.photo_url, absolute=True)
            if isinstance(obj, OrganizationLogo):
                item['image'] = obj.variants.get('160') or (obj.image.url if obj.image else public_asset(obj.static_image, absolute=True))
            items.append(item)
        groups.append({'kind': kind, 'title': title, 'items': items,
                       'create_url': reverse('site-editor-object', args=[kind, 'new']) if kind in ('logo', 'contact') and can(user, kind, 'add') else '',
                       'add_url': reverse(f'admin:{model._meta.app_label}_{model._meta.model_name}_add') if can(user, kind, 'add') else ''})
    return groups


def scope_fields(form, forum):
    for field in form.fields.values():
        if not isinstance(field, forms.ModelChoiceField):
            continue
        model = field.queryset.model
        lookups = {Venue: 'forum', EventDay: 'forum', Speaker: 'forum', Event: 'day__forum', RouteEnterprise: 'event__day__forum',
                   Nomination: 'contest__forum', Contest: 'forum'}
        if model in lookups:
            field.queryset = field.queryset.filter(**{lookups[model]: forum})
        if model is Event and 'event' in form.fields and form._meta.model is Lot:
            field.queryset = field.queryset.filter(kind='exchange')


def make_form(kind, obj, forum, data=None, files=None):
    fields = list(SPECS[kind][3])
    if kind == 'section' and obj.key == 'contest':
        fields = [f for f in fields if f not in ('heading', 'body')]
    widgets = {}
    for name in fields:
        field = obj._meta.get_field(name)
        if isinstance(field, type(Event._meta.get_field('start_time'))):
            widgets[name] = forms.TimeInput(format='%H:%M', attrs={'type': 'time'})
        elif field.get_internal_type() == 'DateTimeField':
            widgets[name] = forms.DateTimeInput(format='%Y-%m-%dT%H:%M', attrs={'type': 'datetime-local'})
        elif field.get_internal_type() == 'DateField':
            widgets[name] = forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'})
        elif field.get_internal_type() == 'TextField':
            widgets[name] = forms.Textarea(attrs={'rows': 4})
        elif name == 'short_position':
            widgets[name] = forms.Textarea(attrs={'rows': 3})
    factory = modelform_factory(type(obj), fields=fields, widgets=widgets)
    form = factory(data=data, files=files, instance=obj)
    scope_fields(form, forum)
    if kind == 'speaker':
        form.fields['photo'].label = 'Общая фотография — для всех мест на сайте'
    return form


def related_forms(kind, obj, forum, user, data=None, files=None):
    groups = []
    definitions = []
    if kind == 'event':
        definitions = [(EventSpeaker, ['speaker', 'role', 'topic', 'position'], 'Выступающие и темы', 'talks')]
        if obj.kind == 'route':
            definitions.append((RouteEnterprise, ['name', 'description', 'position'], 'Предприятия маршрута', 'enterprises'))
    elif kind == 'nominee':
        definitions = [(NomineePhoto, ['image', 'caption', 'position'], 'Фотографии проекта', 'gallery')]
    for model, fields, title, prefix in definitions:
        # Related models retain their own permission checks; editing a parent
        # never grants permission to create, change or delete children.
        permission = f'{model._meta.app_label}.change_{model._meta.model_name}'
        can_delete = user.has_perm(f'{model._meta.app_label}.delete_{model._meta.model_name}')
        factory = inlineformset_factory(type(obj), model, fields=fields, extra=0, can_delete=can_delete,
                                       max_num=100, validate_max=True, absolute_max=120)
        formset = factory(data=data, files=files, instance=obj, prefix=prefix)
        for child in formset:
            scope_fields(child, forum)
        scope_fields(formset.empty_form, forum)
        groups.append({'formset': formset, 'title': title, 'permission': permission, 'model': model,
                       'can_add': user.has_perm(f'{model._meta.app_label}.add_{model._meta.model_name}')})
    return groups


def photo_forms(obj, data=None, files=None):
    factory = modelform_factory(SpeakerPhoto, fields=['image', 'fit', 'focal_x', 'focal_y'])
    existing = {p.placement: p for p in obj.photo_placements.all()}
    result = []
    for placement, title in SpeakerPhoto.PLACEMENTS:
        instance = existing.get(placement) or SpeakerPhoto(speaker=obj, placement=placement,
                            fit='contain' if placement == 'dialog' else 'cover')
        form = factory(data=data, files=files, instance=instance, prefix='photo-'+placement)
        form.fields['image'].label = 'Отдельная фотография (необязательно)'
        result.append({'title': title, 'placement': placement, 'form': form,
                       'original_url': instance.variants.get('400') or (instance.image.url if instance.image else '')})
    return result


@never_cache
@require_GET
def editor(request):
    forum = current_forum()
    groups = catalog(request.user, forum)
    if not groups:
        raise PermissionDenied
    context = {**admin.site.each_context(request), 'title': 'Редактировать сайт',
               'groups': groups, 'editor_catalog': groups}
    return render(request, 'admin/site_editor/index.html', context)


@never_cache
@require_http_methods(['GET', 'POST'])
def edit_object(request, kind, object_id):
    creating = object_id == 'new'
    if kind not in SPECS or not can(request.user, kind, 'add' if creating else 'change'):
        raise PermissionDenied
    if creating and kind not in ('logo', 'contact'):
        raise Http404
    forum = current_forum()
    with transaction.atomic():
        qs = queryset(kind, forum)
        if request.method == 'POST':
            qs = qs.select_for_update()
        if creating:
            obj = SPECS[kind][0](forum=forum)
        else:
            try:
                obj = get_object_or_404(qs, pk=object_id)
            except (ValidationError, ValueError):
                raise Http404
        if not creating and request.method == 'POST' and request.POST.get('_version') != obj.updated_at.isoformat():
            return JsonResponse({'ok': False, 'message': 'Эту запись уже изменили. Откройте её заново, чтобы не затереть изменения коллеги.'}, status=409)
        data, files = (request.POST, request.FILES) if request.method == 'POST' else (None, None)
        form = make_form(kind, obj, forum, data, files)
        groups = related_forms(kind, obj, forum, request.user, data, files)
        groups = [g for g in groups if request.user.has_perm(g['permission'])]
        photos = photo_forms(obj, data, files) if kind == 'speaker' and request.user.has_perm('forums.change_speakerphoto') else []
        message = ''
        status = 200
        if request.method == 'POST':
            valid = form.is_valid()
            for group in groups:
                valid = group['formset'].is_valid() and valid
                model = group['model']
                for child in group['formset']:
                    if not child.has_changed() or not child.cleaned_data:
                        continue
                    action = 'delete' if child.cleaned_data.get('DELETE') else 'change' if child.instance.pk else 'add'
                    if not request.user.has_perm(f'{model._meta.app_label}.{action}_{model._meta.model_name}'):
                        raise PermissionDenied
            for photo in photos:
                valid = photo['form'].is_valid() and valid
                if photo['form'].has_changed() and not photo['form'].instance.pk and not request.user.has_perm('forums.add_speakerphoto'):
                    raise PermissionDenied
            if valid:
                obj = form.save()
                for group in groups:
                    group['formset'].save()
                for photo in photos:
                    if photo['form'].has_changed():
                        photo['form'].save()
                LogEntry.objects.log_actions(user_id=request.user.pk, queryset=[obj], action_flag=ADDITION if creating else CHANGE,
                    change_message='Изменено в визуальном редакторе: '+', '.join(form.changed_data))
                # File widgets use the form's initial value. Rebuild after saving
                # so a first upload is immediately shown with its clear control.
                form = make_form(kind, obj, forum)
                groups = [g for g in related_forms(kind, obj, forum, request.user)
                          if request.user.has_perm(g['permission'])]
                photos = photo_forms(obj) if kind == 'speaker' and request.user.has_perm('forums.change_speakerphoto') else []
                message = 'Сохранено. Изменения уже опубликованы на сайте.'
            else:
                status = 422
                message = 'Проверьте выделенные поля. Изменения пока не сохранены.'
        model = type(obj)
        basic = {
            'event': {'title', 'day', 'start_time', 'end_time', 'venue', 'annotation', 'description', 'contact_name', 'contact_phone', 'is_published'},
            'speaker': {'full_name', 'short_name', 'short_position', 'credentials', 'topic', 'photo', 'is_published'},
            'contest': {'title', 'description', 'rules_text', 'is_open'},
        }.get(kind)
        context = {'form': form, 'groups': groups, 'photos': photos, 'kind': kind, 'obj': obj,
                   'record_title': SPECS[kind][2],
                   'object_id': str(obj.pk), 'label': label(obj), 'message': message,
                   'version': obj.updated_at.isoformat() if obj.updated_at else '', 'saved': request.method == 'POST' and status == 200,
                   'can_delete': kind in ('logo', 'contact') and bool(obj.pk) and can(request.user, kind, 'delete'),
                   'static_base': public_asset(obj.static_photo, absolute=True) if kind == 'speaker' else '',
                   'advanced_url': reverse(f'admin:{model._meta.app_label}_{model._meta.model_name}_change', args=[obj.pk]) if obj.pk else reverse(f'admin:{model._meta.app_label}_{model._meta.model_name}_add'),
                   'speaker_preview': admin.site._registry[Speaker].photo_preview(obj) if kind == 'speaker' else '',
                   'image_fields': [field for field in form if isinstance(field.field, forms.ImageField)]}
        contact_fields = {'contact_name', 'contact_phone'} if kind == 'event' and obj.kind == 'route' else set()
        context['route_contact_fields'] = [f for f in form.visible_fields() if f.name in contact_fields]
        context['basic_fields'] = [f for f in form.visible_fields() if (basic is None or f.name in basic) and f.name not in contact_fields]
        context['advanced_fields'] = [f for f in form.visible_fields() if basic is not None and f.name not in basic]
        html = render_to_string('admin/site_editor/form.html', context, request=request)
        return JsonResponse({'ok': status == 200, 'html': html, 'message': message, 'object_id': str(obj.pk) if obj.pk else 'new',
                             'saved': context['saved'], 'catalog': catalog(request.user, forum) if context['saved'] else None}, status=status)


@never_cache
@require_http_methods(['POST'])
def delete_object(request, kind, object_id):
    if kind not in ('logo', 'contact') or not can(request.user, kind, 'delete'):
        raise PermissionDenied
    with transaction.atomic():
        try:
            obj = get_object_or_404(queryset(kind, current_forum()).select_for_update(), pk=object_id)
        except (ValidationError, ValueError):
            raise Http404
        if request.POST.get('_version') != obj.updated_at.isoformat():
            return JsonResponse({'message': 'Запись уже изменили. Откройте её заново перед удалением.'}, status=409)
        if request.POST.get('confirm') != 'delete':
            return JsonResponse({'message': 'Подтвердите удаление записи.'}, status=400)
        LogEntry.objects.log_actions(user_id=request.user.pk, queryset=[obj], action_flag=DELETION, change_message='Удалено в визуальном редакторе')
        obj.delete()
    return JsonResponse({'ok': True, 'message': 'Запись удалена с сайта.', 'catalog': catalog(request.user, current_forum())})


@never_cache
@require_GET
@xframe_options_sameorigin
def preview(request, page):
    if not catalog(request.user, current_forum()):
        raise PermissionDenied
    if page not in ('forum', 'contest'):
        raise Http404
    root = Path(getattr(settings, 'PUBLIC_SITE_ROOT', settings.BASE_DIR.parent / 'site'))
    file = root / ('index.html' if page == 'forum' else 'contest/index.html')
    if not file.is_file():
        return HttpResponse('Предпросмотр недоступен: файлы сайта не подключены.', status=503)
    html = file.read_text()
    base = settings.PUBLIC_SITE_URL
    html = re.sub(r'((?:src|href)=["\'])(/(?:css|fonts|js|img|promtour)/)', lambda m: m[1]+base+m[2], html)
    html = html.replace('"/deployment-config.json", ', '')
    bridge = '<script>window.FORUM_EDITOR_PREVIEW=true;window.forumInitialData=window.forumInitialData||{};window.forumInitialData["/deployment-config.json"]=Promise.resolve({submissions_enabled:0,voting_enabled:0});</script>'
    version = sha256((settings.BASE_DIR / 'accounts/static/workspace/editor-preview.js').read_bytes()).hexdigest()[:12]
    bridge += '<script src="/static/workspace/editor-preview.js?v='+version+'" defer></script>'
    html = html.replace('</head>', bridge+'</head>')
    response = HttpResponse(html)
    response['Content-Security-Policy'] = "frame-ancestors 'self'"
    return response


def urls():
    wrap = admin.site.admin_view
    return [path('site-editor/', wrap(editor), name='site-editor'),
            path('site-editor/object/<str:kind>/<str:object_id>/delete/', wrap(delete_object), name='site-editor-delete'),
            path('site-editor/object/<str:kind>/<str:object_id>/', wrap(edit_object), name='site-editor-object'),
            path('site-editor/preview/<str:page>/', wrap(preview), name='site-editor-preview')]
