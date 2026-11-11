import time

from django.core.management.base import BaseCommand

from registrations.notifications import process_batch


class Command(BaseCommand):
    help = 'Обрабатывает NotificationOutbox с блокировками и повторными попытками.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--loop', action='store_true')
        parser.add_argument('--sleep', type=int, default=5)
        parser.add_argument('--limit', type=int, default=20)

    def handle(self, *args, **options):
        if options['once'] and options['loop']:
            self.stderr.write('Выберите только один режим: --once или --loop.')
            return
        if options['loop']:
            try:
                while True:
                    counts = process_batch(options['limit'])
                    if counts['empty']:
                        time.sleep(options['sleep'])
                    else:
                        self.stdout.write(str(counts))
            except KeyboardInterrupt:
                return
        else:
            counts = process_batch(options['limit'])
            self.stdout.write(str(counts))
