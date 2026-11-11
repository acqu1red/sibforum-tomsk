import re
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from forums.models import Forum
from voting.models import Contest, Nomination, Nominee

TITLES = (
    'Лучший бренд ТО',
    'Лучший промышленный маршрут',
    'Корпоративный музей как точка притяжения',
    'Креативное продвижение промышленного туризма',
    'Профориентационный тур года',
    'Самый доступный промышленный тур',
    'Лучший гид по промышленному туризму',
    'Лучшая сувенирная продукция предприятия',
)
NS = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}


class Command(BaseCommand):
    help = 'Импортирует номинации и кандидатов из DOCX-таблицы конкурса.'

    def add_arguments(self, parser):
        parser.add_argument('path', type=str)
        parser.add_argument('--forum', default='promtour')

    def cell_text(self, cell):
        paragraphs = []
        for paragraph in cell.findall('.//w:p', NS):
            text = ''.join(node.text or '' for node in paragraph.findall('.//w:t', NS))
            paragraphs.append(text)
        return re.sub(r'\s+', ' ', ' '.join(paragraphs)).strip()

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError('Импорт в этой команде разрешён только при DEBUG=1.')
        forum = Forum.objects.filter(slug=options['forum'], status=Forum.Status.PUBLISHED).first()
        if not forum:
            raise CommandError('Опубликованный форум не найден.')
        path = Path(options['path'])
        if not path.exists():
            raise CommandError(f'Файл не найден: {path}')
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read('word/document.xml'))
        table = root.find('.//w:tbl', NS)
        if table is None:
            raise CommandError('В DOCX не найдена таблица номинаций.')
        contest, _ = Contest.objects.update_or_create(
            forum=forum,
            defaults={
                'title': 'Индустриальный код',
                'description': 'Онлайн-голосование за лучшие проекты Томской области в сфере промышленного туризма.',
                'rules_text': 'Можно пропустить незнакомую номинацию. Не более одного голоса за кандидата в каждой номинации. Один подтверждённый email = один бюллетень.',
                'is_open': True,
                'voting_opens_at': timezone.now() - timezone.timedelta(hours=1),
                'voting_closes_at': forum.ends_at,
                'results_published': False,
            },
        )
        current = None
        candidate_position = 0
        counts = {'nominations': 0, 'nominees': 0}
        for row in table.findall('./w:tr', NS):
            cells = [self.cell_text(cell) for cell in row.findall('./w:tc', NS)]
            if len(cells) < 4:
                continue
            number, nomination_cell, candidate_cell, description_cell = cells[:4]
            if number == '№':
                continue
            if number.isdigit():
                index = int(number)
                current, _ = Nomination.objects.update_or_create(
                    contest=contest,
                    title=TITLES[index - 1],
                    defaults={
                        'visual_group': 1 if index <= 3 else 0,
                        'min_selections': 0,
                        'max_selections': 1,
                        'position': index,
                        'is_active': True,
                    },
                )
                counts['nominations'] += 1
                candidate_position = 0
                name, description = candidate_cell or description_cell, description_cell if candidate_cell else ''
            elif nomination_cell in TITLES:
                index = TITLES.index(nomination_cell) + 1
                current, _ = Nomination.objects.update_or_create(
                    contest=contest,
                    title=nomination_cell,
                    defaults={
                        'visual_group': 1 if index <= 3 else 0,
                        'min_selections': 0,
                        'max_selections': 1,
                        'position': index,
                        'is_active': True,
                    },
                )
                counts['nominations'] += 1
                candidate_position = 0
                name, description = candidate_cell or description_cell, description_cell if candidate_cell else ''
            else:
                name, description = candidate_cell, description_cell
            if not current or not name or name.startswith('????'):
                continue
            candidate_position += 1
            website = ''
            match = re.search(r'https?://[^\s]+', description)
            if match:
                website = match.group(0).rstrip('.,;)')
            Nominee.objects.update_or_create(
                nomination=current,
                name=name[:500],
                defaults={
                    'description': description,
                    'website_url': website,
                    'position': candidate_position,
                    'is_active': True,
                },
            )
            counts['nominees'] += 1
        if counts['nominations'] != 8:
            raise CommandError(f'Ожидалось 8 номинаций, найдено {counts["nominations"]}.')
        self.stdout.write(self.style.SUCCESS(f'Импортировано: {counts["nominations"]} номинаций, {counts["nominees"]} кандидатов.'))
