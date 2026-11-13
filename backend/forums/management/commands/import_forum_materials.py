"""Apply an explicit, reviewed material manifest without reloading a forum."""
import hashlib
import json
import re
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from forums.media import image_variants, validate_image_upload
from forums.models import Event, Forum, InterfaceText, OrganizationLogo, Speaker
from voting.models import Nominee, NomineePhoto


class Command(BaseCommand):
    help = 'Проверить и применить согласованный список материалов; существующие файлы и тексты сохраняются.'

    def add_arguments(self, parser):
        parser.add_argument('manifest')
        parser.add_argument('--directory', required=True)
        parser.add_argument('--apply', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        manifest = json.loads(Path(options['manifest']).read_text())
        root = Path(options['directory']).resolve()
        forum = Forum.objects.get(slug=manifest.get('forum', 'promtour'))
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}', manifest.get('batch', '')):
            raise CommandError('Недопустимое имя пакета.')
        apply = options['apply']
        stats = {'mode': 'apply' if apply else 'preview', 'logos': 0, 'photos': 0, 'patches': 0, 'event_organizers': 0, 'existing_files_kept': 0}
        cache = {}
        variant_cache = {}
        targets = {'forums.organizationlogo': (OrganizationLogo, 'forum'), 'voting.nominee': (Nominee, 'nomination__contest__forum')}
        patch_targets = {**targets, 'forums.event': (Event, 'day__forum'), 'forums.interfacetext': (InterfaceText, 'forum')}
        allowed = {'forums.organizationlogo': {'show_name'}, 'forums.event': {'contact_name', 'contact_phone', 'description', 'start_time'}, 'forums.interfacetext': {'value'}}

        def target(model, pk, mapping):
            cls, lookup = mapping[model]
            try:
                return cls.objects.select_for_update().get(pk=pk, **{lookup: forum})
            except cls.DoesNotExist as exc:
                raise CommandError(f'Запись {model}:{pk} отсутствует в этом форуме.') from exc

        def source(relative):
            path = (root / relative).resolve()
            if not path.is_relative_to(root) or not path.is_file():
                raise CommandError(f'Недоступен файл: {relative}')
            raw = path.read_bytes()
            validate_image_upload(SimpleUploadedFile(path.name, raw))
            return path, raw

        def assign_file(obj, field_name, relative):
            path, raw = source(relative)
            if not apply:
                return
            digest = hashlib.sha256(raw).hexdigest()
            field = getattr(obj, field_name)
            if digest not in cache:
                name = f'materials/{manifest["batch"]}/{digest}{path.suffix.lower()}'
                if not field.storage.exists(name):
                    name = field.storage.save(name, ContentFile(raw))
                cache[digest] = name
            field.name = cache[digest]
            if digest not in variant_cache:
                variant_cache[digest] = image_variants(field)
            setattr(obj, 'logo_variants' if field_name == 'logo' else 'variants', variant_cache[digest])

        # Compare only fields explicitly authorized in the manifest. A colleague's
        # unrelated edits do not conflict and are never written back by this job.
        for entry in manifest.get('patches', []):
            model = entry['model']
            if model not in allowed or not set(entry['changes']).issubset(allowed[model]):
                raise CommandError('Изменение поля вне разрешённого списка.')
            obj = target(model, entry['id'], patch_targets)
            changes = {}
            for field, value in entry['changes'].items():
                model_field = obj._meta.get_field(field)
                value = model_field.to_python(value)
                current = getattr(obj, field)
                if current == value:
                    continue
                if field not in entry['expected'] or current != model_field.to_python(entry['expected'][field]):
                    raise CommandError(f'Запись {model}:{obj.pk}, поле {field} изменено редактором. Обновите план.')
                changes[field] = value
            if changes:
                stats['patches'] += 1
                if apply:
                    for field, value in changes.items():
                        setattr(obj, field, value)
                    obj.save(update_fields=(*changes, 'updated_at'))

        for entry in manifest.get('logos', []):
            if entry['model'] not in targets:
                raise CommandError('Неизвестный тип логотипа.')
            obj = target(entry['model'], entry['id'], targets)
            field_name, fallback = ('image', 'static_image') if isinstance(obj, OrganizationLogo) else ('logo', 'static_logo')
            if getattr(obj, field_name) or getattr(obj, fallback):
                stats['existing_files_kept'] += 1
                continue
            assign_file(obj, field_name, entry['file'])
            stats['logos'] += 1
            if apply:
                if isinstance(obj, OrganizationLogo):
                    obj.image_background = entry.get('background', 'light')
                obj.save()

        for entry in manifest.get('galleries', []):
            nominee = target('voting.nominee', entry['nominee_id'], targets)
            position = max(nominee.photos.values_list('position', flat=True), default=-1) + 1
            for i, relative in enumerate(entry['files']):
                path, raw = source(relative)
                digest = hashlib.sha256(raw).hexdigest()
                # Stable content-based names make repeated execution append-free.
                expected_name = f'materials/{manifest["batch"]}/{digest}{path.suffix.lower()}'
                existing = list(nominee.photos.all())
                if any(p.image.name == expected_name or '/optimized/' + digest[:24] + '-' in p.variants.get('960', '') for p in existing):
                    continue
                photo = NomineePhoto(nominee=nominee, caption=entry['caption'] + f' · фото {i+1}', position=position)
                assign_file(photo, 'image', relative)
                stats['photos'] += 1
                if apply:
                    photo.save()
                position += 1

        for entry in manifest.get('event_organizers', []):
            event = target('forums.event', entry['event_id'], patch_targets)
            speaker = Speaker.objects.get(pk=entry['source_speaker_id'], forum=forum)
            if not speaker.photo and not speaker.static_photo:
                raise CommandError('У компании отсутствует исходный логотип.')
            organization = OrganizationLogo.objects.filter(forum=forum, group='events', name=entry['name']).first()
            if event.organizer_id and (not organization or event.organizer_id != organization.pk):
                raise CommandError('Организатор мероприятия уже изменён. Обновите план.')
            stats['event_organizers'] += 1
            if apply:
                if not organization:
                    organization = OrganizationLogo.objects.create(forum=forum, group='events', name=entry['name'],
                        image=speaker.photo.name, variants=speaker.photo_variants, static_image=speaker.static_photo,
                        image_background='light', position=0, is_published=True)
                if event.organizer_id != organization.pk:
                    event.organizer = organization
                    event.save(update_fields=('organizer', 'updated_at'))
        self.stdout.write(json.dumps(stats, ensure_ascii=False))
