from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group
from accounts.roles import ROLE_CHOICES, role_permissions


class Command(BaseCommand):
    help = 'Обновить права стандартных ролей после добавления разделов сайта.'

    def handle(self, *args, **options):
        for role, name in ROLE_CHOICES:
            group = Group.objects.filter(name=name).first()
            if not group:
                continue
            group.permissions.set(role_permissions(role))
        self.stdout.write('Права стандартных ролей обновлены; индивидуальные роли сохранены.')
