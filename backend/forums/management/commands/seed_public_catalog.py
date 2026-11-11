from django.core.management import call_command
from django.core.management.base import BaseCommand
from forums.models import Forum


class Command(BaseCommand):
    help = 'Заполнить только пустую локальную БД публичным каталогом.'

    def add_arguments(self, parser):
        parser.add_argument('fixture')

    def handle(self, *args, **options):
        if Forum.objects.exists():
            self.stdout.write('Каталог уже существует; повторный импорт пропущен.')
        else:
            call_command('loaddata', options['fixture'])
