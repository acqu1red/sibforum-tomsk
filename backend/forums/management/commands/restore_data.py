import os
import tarfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Восстанавливает БД и media только при RESTORE_CONFIRM=1.'

    def add_arguments(self, parser):
        parser.add_argument('path', type=str)

    def handle(self, *args, **options):
        if os.environ.get('RESTORE_CONFIRM') != '1':
            raise CommandError('Восстановление подтверждается только через RESTORE_CONFIRM=1.')
        path = Path(options['path'])
        if not path.is_file():
            raise CommandError(f'Резервная копия не найдена: {path}')
        call_command('loaddata', str(path))
        media_path = path.with_name(path.stem + '-media.tar.gz')
        if media_path.is_file():
            settings.MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
            with tarfile.open(media_path, 'r:gz') as archive:
                archive.extractall(settings.MEDIA_ROOT, filter='data')
        self.stdout.write(self.style.SUCCESS(f'Восстановление завершено: {path}'))
