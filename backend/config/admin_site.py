from django.conf import settings
from django.contrib.admin import AdminSite, ModelAdmin
from django.urls import reverse
from functools import lru_cache
from hashlib import sha256
from pathlib import Path


@lru_cache(maxsize=1)
def workspace_asset_version():
    folder = Path(settings.BASE_DIR) / 'accounts/static/workspace'
    return sha256(b''.join((folder / name).read_bytes() for name in ('admin.css', 'admin.js'))).hexdigest()[:12]


class WorkspaceTitles:
    def changelist_view(self, request, extra_context=None):
        context = dict(extra_context or {})
        context['title'] = self.model._meta.verbose_name_plural
        return super().changelist_view(request, extra_context=context)

    def changeform_view(self, request, object_id=None, form_url='', extra_context=None):
        context = dict(extra_context or {})
        new_titles = {
            'user': 'Новый сотрудник', 'group': 'Новая роль', 'forum': 'Новый форум',
            'venue': 'Новая площадка', 'eventday': 'Новый день программы',
            'event': 'Новое мероприятие', 'speaker': 'Новый спикер',
            'contest': 'Новый конкурс', 'nomination': 'Новая номинация',
            'nominee': 'Новый кандидат', 'lot': 'Новый лот биржи',
            'participant': 'Новый участник', 'choicegroup': 'Новое правило выбора',
        }
        context['title'] = (new_titles.get(self.model._meta.model_name, 'Новая запись')
                            if object_id is None else self.model._meta.verbose_name_plural + ' · Редактирование')
        return super().changeform_view(request, object_id, form_url, context)


class ForumAdminSite(AdminSite):
    site_header = 'Сибирский форум'
    site_title = 'Управление форумом'
    index_title = 'Обзор'
    enable_nav_sidebar = True
    site_url = None

    def register(self, model_or_iterable, admin_class=None, **options):
        original = admin_class or ModelAdmin
        friendly = type('Workspace' + original.__name__, (WorkspaceTitles, original), {'__module__': original.__module__})
        return super().register(model_or_iterable, friendly, **options)

    def each_context(self, request):
        context = super().each_context(request)
        owner = request.user.is_authenticated and request.user.is_superuser and request.user.get_username() == settings.ADMIN_OWNER_USERNAME
        sections = [
            ('Работа с участниками', [
                ('Заявки', 'registrations', 'registration', 'Все заявки и подтверждения участников'),
                ('Модерация', 'registrations', 'registrationitem', 'Одобрение, отклонение и перенос на другой маршрут'),
                ('Участники', 'registrations', 'participant', 'Контакты, организации и поиск по имени'),
                ('Билеты', 'registrations', 'ticket', 'Выданные билеты и их статусы'),
            ]),
            ('Содержание форума', [
                ('Форумы и площадки', 'forums', 'forum', 'Даты, описание форума и адреса площадок'),
                ('Программа', 'forums', 'event', 'Мероприятия, время, маршруты и количество мест'),
                ('Спикеры', 'forums', 'speaker', 'Фотографии, регалии и темы выступлений'),
                ('Лоты биржи', 'registrations', 'lot', 'Заказчики и технические материалы'),
            ]),
            ('Конкурс', [
                ('Конкурсы', 'voting', 'contest', 'Сроки голосования, правила и публикация итогов'),
                ('Номинации и кандидаты', 'voting', 'nomination', 'Список номинаций и их кандидатов'),
            ]),
            ('Контроль', [
                ('Письма', 'registrations', 'notificationoutbox', 'Очередь отправки и ошибки доставки'),
                ('История изменений', 'registrations', 'registrationitemhistory', 'Кто и когда изменял заявки'),
            ]),
        ]
        navigation = []
        for title, entries in sections:
            links = []
            for label, app, model, description in entries:
                if request.user.is_authenticated and (request.user.has_perm(f'{app}.view_{model}') or request.user.has_perm(f'{app}.change_{model}')):
                    url = reverse(f'admin:{app}_{model}_changelist')
                    links.append({'label': label, 'url': url, 'description': description,
                                  'active': request.path.startswith(url)})
            if links:
                navigation.append({'title': title, 'links': links})
        if owner:
            navigation.append({'title': 'Команда', 'links': [
                {'label': 'Сотрудники', 'url': reverse('admin:auth_user_changelist'), 'description': 'Аккаунты, пароли и доступ к панели', 'active': '/auth/user/' in request.path},
                {'label': 'Роли и права', 'url': reverse('admin:auth_group_changelist'), 'description': 'Какие разделы доступны сотрудникам', 'active': '/auth/group/' in request.path},
            ]})
        context.update({
            'workspace_navigation': navigation,
            'workspace_is_owner': owner,
            'workspace_name': ('Руководитель' if owner else request.user.get_full_name() or request.user.get_username()) if request.user.is_authenticated else '',
            'workspace_public_url': settings.PUBLIC_SITE_URL,
            'workspace_asset_version': workspace_asset_version(),
        })
        return context

    def index(self, request, extra_context=None):
        from registrations.models import Registration, RegistrationItem, NotificationOutbox
        from forums.models import Event, Speaker
        from voting.models import Contest
        extra = dict(extra_context or {})
        definitions = [
            ('Заявки участников', Registration, 'registrations.view_registration', {}, 'admin:registrations_registration_changelist', ''),
            ('Ожидают решения', RegistrationItem, 'registrations.view_registrationitem', {'status': 'pending_review'}, 'admin:registrations_registrationitem_changelist', '?status__exact=pending_review'),
            ('Мероприятия', Event, 'forums.view_event', {}, 'admin:forums_event_changelist', ''),
            ('Письма с ошибкой', NotificationOutbox, 'registrations.view_notificationoutbox', {'status': 'failed'}, 'admin:registrations_notificationoutbox_changelist', '?status__exact=failed'),
        ]
        extra['workspace_metrics'] = [
            {'label': label, 'count': model.objects.filter(**filters).count(), 'url': reverse(url) + query}
            for label, model, permission, filters, url, query in definitions if request.user.has_perm(permission)
        ]
        extra['workspace_forums'] = []
        if request.user.has_perm('forums.view_forum'):
            from forums.models import Forum
            extra['workspace_forums'] = Forum.objects.all()[:5]
        extra['workspace_can_checkin'] = request.user.has_perm('registrations.add_checkin')
        extra['workspace_can_export'] = request.user.has_perm('registrations.view_registration')
        return super().index(request, extra)
