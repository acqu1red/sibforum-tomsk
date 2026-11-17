import json
import secrets
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from accounts.roles import assign_role


class Command(BaseCommand):
    help = 'Создать два ограниченных аккаунта. JSON с паролями направлять только в приватный файл вне Git.'

    def add_arguments(self, parser):
        parser.add_argument('--prefix', default='')

    @transaction.atomic
    def handle(self, *args, **options):
        result = []
        for suffix, role, name in [('entry_admin', 'checkin', 'Администратор на входе'), ('event_moderator', 'moderator', 'Модератор экскурсий')]:
            username = options['prefix'] + suffix
            if get_user_model().objects.filter(username=username).exists():
                raise CommandError('Аккаунт уже существует. Пароли существующих пользователей не изменены.')
            password = secrets.token_urlsafe(18)
            user = get_user_model().objects.create_user(username=username, password=password, is_staff=True, first_name=name)
            assign_role(user, role)
            result.append({'username': username, 'password': password, 'role': role})
        self.stdout.write(json.dumps(result, ensure_ascii=False))
