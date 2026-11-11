import tarfile
import json
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.utils import timezone


class Command(BaseCommand):
    help = 'Сохраняет БД и локальные media либо опись версий S3; хранит 14 комплектов.'

    def add_arguments(self, parser):
        parser.add_argument('--dir', default=str(settings.BASE_DIR / 'backups'))

    def handle(self, *args, **options):
        directory = Path(options['dir'])
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"backup-{timezone.now():%Y%m%d-%H%M%S}.json"
        media_path = path.with_name(path.stem + '-media.tar.gz')
        call_command('dumpdata', format='json', indent=2, exclude=['contenttypes', 'auth.permission'], output=str(path))
        inventory_path = path.with_name(path.stem + '-s3-inventory.ndjson')
        if settings.MEDIA_BUCKET_NAME:
            # Originals stay in Object Storage. Versioning retains replaced/deleted
            # objects; this manifest records exact version IDs for a DB restore.
            client = default_storage.connection.meta.client
            with inventory_path.open('w') as output:
                for page in client.get_paginator('list_object_versions').paginate(Bucket=settings.MEDIA_BUCKET_NAME):
                    for kind in ('Versions', 'DeleteMarkers'):
                        for item in page.get(kind, []):
                            output.write(json.dumps({'kind': kind, **item}, default=str) + '\n')
            media_path = inventory_path
        else:
            with tarfile.open(media_path, 'w:gz') as archive:
                if settings.MEDIA_ROOT.exists():
                    archive.add(settings.MEDIA_ROOT, arcname='.')
        backups = sorted(directory.glob('backup-*.json'), key=lambda item: item.stat().st_mtime, reverse=True)
        for old in backups[14:]:
            old.unlink()
            old_media = old.with_name(old.stem + '-media.tar.gz')
            if old_media.exists():
                old_media.unlink()
            old_inventory = old.with_name(old.stem + '-s3-inventory.ndjson')
            if old_inventory.exists():
                old_inventory.unlink()
        self.stdout.write(self.style.SUCCESS(f'Создана резервная копия: {path}, {media_path}; хранится комплектов: {min(len(backups), 14)}.'))
