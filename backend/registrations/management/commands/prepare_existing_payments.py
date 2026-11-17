from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from registrations.models import RegistrationItem, Registration
from registrations.payments import request_payment
from registrations.tickets import ensure_ticket
from forums.models import Forum


class Command(BaseCommand):
    help = 'Пометить прежние одобренные платные заявки как непроверенные. Не отправляет писем и не подтверждает оплату.'

    def add_arguments(self, parser):
        parser.add_argument('--forum', required=True)
        parser.add_argument('--expected', type=int, required=True)

    @transaction.atomic
    def handle(self, *args, **options):
        forum = Forum.objects.select_for_update().get(slug=options['forum'])
        items = list(RegistrationItem.objects.select_for_update(of=('self',)).filter(
            registration__participant__forum=forum, event__is_paid=True, status='approved', payment_status='not_required'))
        if len(items) != options['expected']:
            raise CommandError(f'Ожидалось {options["expected"]} прежних заявок; найдено {len(items)}. Изменения отменены.')
        for item in items:
            request_payment(item)
            item.save(update_fields=('payment_status', 'payment_request_id', 'payment_amount', 'payment_instruction'))
        for registration in Registration.objects.filter(id__in={item.registration_id for item in items}):
            ensure_ticket(registration)
        self.stdout.write(f'Помечено непроверенными: {len(items)}. Писем и подтверждений оплаты не создано.')
