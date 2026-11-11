import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from forums.models import ForumPage, OrganizationLogo


class Command(BaseCommand):
    help = 'Однократно перенести два согласованных блока логотипов. Повторный запуск не меняет правки редактора.'

    def add_arguments(self, parser):
        parser.add_argument('manifest')

    @transaction.atomic
    def handle(self, *args, **options):
        page = ForumPage.objects.select_for_update().get(forum__slug='promtour')
        if page.reference_logos_imported:
            self.stdout.write('Логотипы уже перенесены. Редакторские изменения сохранены.')
            return
        records = json.loads(Path(options['manifest']).read_text())['records']
        if not records or any(r['group'] not in ('organizers', 'enterprises') or not r['image'].startswith('/img/logos/reference-forum/') for r in records):
            raise CommandError('Ожидался согласованный список двух блоков с локальными путями изображений.')
        # Keep previous entries available in the admin, without publishing a
        # second conflicting list alongside the reference requested by the owner.
        page.forum.organization_logos.filter(group__in=('organizers', 'enterprises')).update(is_published=False)
        for record in records:
            obj, _ = OrganizationLogo.objects.get_or_create(forum=page.forum, group=record['group'], name=record['name'])
            obj.static_image = record['image']
            obj.image_background = record['background']
            obj.position = record['position']
            obj.is_published = True
            obj.save()
        page.reference_logos_imported = True
        page.save(update_fields=('reference_logos_imported', 'updated_at'))
        self.stdout.write(self.style.SUCCESS(f'Перенесено {len(records)} логотипов; прежние записи сохранены в панели без публикации.'))
