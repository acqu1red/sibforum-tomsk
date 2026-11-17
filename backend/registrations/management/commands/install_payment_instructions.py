from hashlib import sha256
from io import BytesIO
from pathlib import Path
from PIL import Image
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from forums.models import Forum
from registrations.models import PaymentInstruction


class Command(BaseCommand):
    help = 'Установить предоставленный владельцем PDF оплаты и проверенное PNG-представление. Писем не отправляет.'

    def add_arguments(self, parser):
        parser.add_argument('--forum', required=True)
        parser.add_argument('--pdf', required=True)
        parser.add_argument('--png', required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        forum = Forum.objects.select_for_update().filter(slug=options['forum']).first()
        if not forum:
            raise CommandError('Форум не найден')
        pdf, png = Path(options['pdf']).read_bytes(), Path(options['png']).read_bytes()
        if not pdf.startswith(b'%PDF-') or len(pdf) > 5_000_000 or len(png) > 5_000_000:
            raise CommandError('Неверный формат или размер файлов')
        with Image.open(BytesIO(png)) as image:
            if image.format != 'PNG' or image.width * image.height > 10_000_000:
                raise CommandError('Неверное PNG-представление')
            image.verify()
        digest = sha256(pdf).hexdigest()
        current = PaymentInstruction.objects.filter(forum=forum).first()
        if current and current.pdf_sha256 == digest and bytes(current.qr_png) == png:
            self.stdout.write('Платёжные реквизиты уже установлены; писем не создано.')
            return
        value = PaymentInstruction.objects.create(forum=forum, source_filename=Path(options['pdf']).name,
            pdf_bytes=pdf, qr_png=png, pdf_sha256=digest)
        self.stdout.write(f'Установлена версия {value.id}; SHA-256 {digest}; писем не создано.')
