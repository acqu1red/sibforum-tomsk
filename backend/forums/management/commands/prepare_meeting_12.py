"""Add the agreed controls; never reload a catalog over an existing forum."""
import re

from django.core.management.base import BaseCommand
from django.db import transaction

from forums.interface import TEXTS
from forums.models import Forum, ForumPage, InterfaceText, OrganizationLogo, RouteEnterprise


def normalized(value):
    return re.sub(r'[^а-яa-z0-9]', '', value.lower().replace('ё', 'е'))


def prepare_controls(forum):
    for key, (_, default) in TEXTS.items():
        InterfaceText.objects.get_or_create(forum=forum, key=key, defaults={'value': default})


def prepare_organizations(forum):
    page, _ = ForumPage.objects.get_or_create(forum=forum)
    if page.meeting_12_organizations_applied:
        return False
    organizers = [
        ('Торгово-промышленная палата Российской Федерации', '/img/logos/organizers/00-tpp-rf.jpg', 'light', 'российскойфедерации'),
        ('Союз «Торгово-промышленная палата Томской области»', '/img/logos/reference-forum/organizers-1.png', 'dark', 'палататомскойобласти'),
        ('Администрация Томской области', '/img/logos/reference-forum/organizers-2.png', 'dark', 'администрациятомскойобласти'),
        ('Томский политехнический университет', '/img/logos/organizers/06-tomskiy-politeh.png', 'dark', 'томскийполитехническийуниверситет'),
    ]
    selected = []
    existing = list(forum.organization_logos.filter(group='organizers').order_by('-is_published', 'position', 'pk'))
    for position, (name, image, background, fragment) in enumerate(organizers):
        obj = next((logo for logo in existing if fragment in normalized(logo.name)), None)
        if obj is None:
            obj = OrganizationLogo(forum=forum, group='organizers', name=name, static_image=image, image_background=background)
        if not obj.image and not obj.static_image:
            obj.static_image = image
            obj.image_background = background
        if not obj.image and obj.static_image == image:
            obj.image_background = background
        obj.position = position
        obj.is_published = True
        obj.save()
        selected.append(obj.pk)
    # Keep originals available to the editor. Only the agreed four remain public.
    for logo in forum.organization_logos.filter(group='organizers').exclude(pk__in=selected):
        if logo.is_published:
            logo.is_published = False
            logo.save(update_fields=('is_published', 'updated_at'))
    candidates = list(forum.organization_logos.filter(group='enterprises').order_by('-is_published', 'position', 'pk'))
    selected = []
    for position, enterprise in enumerate(RouteEnterprise.objects.filter(event__day__forum=forum, event__kind='route', event__is_published=True).select_related('event__day').order_by('event__day__position', 'event__position', 'position', 'pk')):
        obj = next((logo for logo in candidates if normalized(logo.name) == normalized(enterprise.name)), None)
        if obj is None:
            obj = OrganizationLogo(forum=forum, group='enterprises', name=enterprise.name)
        obj.route_enterprise = enterprise
        obj.position = position
        obj.is_published = True
        obj.save()
        selected.append(obj.pk)
    for logo in forum.organization_logos.filter(group='enterprises').exclude(pk__in=selected):
        if logo.is_published:
            logo.is_published = False
            logo.save(update_fields=('is_published', 'updated_at'))
    # The meeting explicitly separates this university from the organizers.
    OrganizationLogo.objects.get_or_create(forum=forum, group='partners', name='ТУСУР', defaults={
        'static_image': '/img/logos/organizers/08-tusur.png', 'image_background': 'dark', 'position': 0, 'is_published': True,
    })
    page.meeting_12_organizations_applied = True
    page.save(update_fields=('meeting_12_organizations_applied', 'updated_at'))
    return True


class Command(BaseCommand):
    help = 'Добавить настройки встречи 12.11 без перезаписи текстов, спикеров, фото, заявок или голосов.'

    def add_arguments(self, parser):
        parser.add_argument('--slug', default='promtour')
        parser.add_argument('--apply-organizations', action='store_true', help='Однократно применить согласованные четыре организатора и предприятия маршрутов.')

    @transaction.atomic
    def handle(self, *args, **options):
        forum = Forum.objects.get(slug=options['slug'])
        prepare_controls(forum)
        applied = prepare_organizations(forum) if options['apply_organizations'] else False
        self.stdout.write(self.style.SUCCESS('Недостающие подписи добавлены; существующие тексты сохранены. ' + ('Согласованные группы организаций обновлены.' if applied else 'Повторная перезапись организаций не выполнялась.')))
