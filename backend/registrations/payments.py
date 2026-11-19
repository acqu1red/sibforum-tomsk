"""Manual receipt verification. Never contacts a bank or charges a participant."""
import uuid
from .models import PaymentInstruction, PaymentConfirmation, RegistrationItem
from .selection import RegistrationError


def request_payment(item):
    instruction = PaymentInstruction.objects.filter(forum=item.registration.participant.forum).first()
    if not instruction:
        raise RegistrationError('payment_not_configured', 'Сначала загрузите согласованный платёжный QR для форума.', status=409)
    if item.event.price is None or item.event.price <= 0:
        raise RegistrationError('payment_amount_missing', 'Проверьте стоимость платной экскурсии.', status=409)
    item.payment_status = RegistrationItem.PaymentStatus.AWAITING
    item.payment_request_id = uuid.uuid4()
    item.payment_amount = item.event.price
    item.payment_instruction = instruction


def confirm_payment(item, actor, note):
    if not actor.has_perm('registrations.confirm_payment'):
        raise RegistrationError('forbidden', 'Нет права подтверждать оплату.', status=403)
    if item.status != RegistrationItem.Status.APPROVED or not item.event.is_paid or item.payment_status != RegistrationItem.PaymentStatus.AWAITING:
        raise RegistrationError('invalid_transition', 'Эта заявка не ожидает подтверждения оплаты.', status=409)
    if not item.payment_request_id or not item.payment_instruction_id or item.payment_amount is None:
        raise RegistrationError('payment_not_configured', 'Не сохранены реквизиты запроса оплаты. Обратитесь к руководителю.', status=409)
    PaymentConfirmation.objects.create(item=item, request_id=item.payment_request_id, event=item.event,
        amount=item.payment_amount, instruction=item.payment_instruction, actor=actor,
        note=note or 'Квитанция проверена, оплата подтверждена модератором')
    item.payment_status = RegistrationItem.PaymentStatus.CONFIRMED


def send_payment_request(item, actor):
    from .workflow import queue_notification, decision_personal_url
    from .selection import add_history
    from .models import RegistrationItemHistory, NotificationOutbox
    if not actor.has_perm('registrations.confirm_payment'):
        raise RegistrationError('forbidden', 'Нет права запрашивать оплату.', status=403)
    if item.status != RegistrationItem.Status.APPROVED or not item.event.is_paid or item.payment_status != RegistrationItem.PaymentStatus.AWAITING or not item.payment_request_id:
        raise RegistrationError('invalid_transition', 'Эта заявка не ожидает оплаты.', status=409)
    key = f'payment-request:{item.payment_request_id}'
    if NotificationOutbox.objects.filter(dedup_key=key).exists():
        raise RegistrationError('already_requested', 'Письмо с QR уже отправлено или находится в очереди. Повтор не создан.', status=409)
    queue_notification(item.registration, 'payment_request', item.registration.participant.email, {
        'item_id': str(item.id), 'event': item.event.title, 'payment_request_id': str(item.payment_request_id),
        'payment_instruction': str(item.payment_instruction_id), 'payment_amount': str(item.payment_amount),
        'personal_url': decision_personal_url(item.registration),
    }, key)
    add_history(item, 'payment_requested', item.status, RegistrationItemHistory.ActorKind.ADMIN,
        from_status=item.status, actor_user=actor, note='Вручную отправлено письмо с платёжным QR')
