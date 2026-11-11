from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from accounts.roles import ROLE_CHOICES


class Command(BaseCommand):
    help = 'Обновить права стандартных ролей после добавления разделов сайта.'

    def handle(self, *args, **options):
        for role, name in ROLE_CHOICES:
            group = Group.objects.filter(name=name).first()
            if not group:
                continue
            permissions = Permission.objects.filter(content_type__app_label__in=['forums', 'registrations', 'voting'])
            app = {'content': 'forums', 'contest': 'voting', 'registration': 'registrations'}.get(role)
            if app:
                permissions = permissions.filter(content_type__app_label=app).exclude(codename__startswith='delete_')
            elif role == 'viewer':
                permissions = permissions.filter(codename__startswith='view_')
            group.permissions.set(permissions)
        self.stdout.write('Права стандартных ролей обновлены; индивидуальные роли сохранены.')
