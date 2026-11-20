from django.db.models import Q
from .models import RegistrationItem


def eligible_items(items):
    return items.filter(status__in=(RegistrationItem.Status.CONFIRMED, RegistrationItem.Status.APPROVED)).filter(
        Q(event__is_paid=False) | Q(payment_status=RegistrationItem.PaymentStatus.CONFIRMED))


def ticket_has_admission(ticket, event):
    items = eligible_items(ticket.registration.items)
    if event is not None:
        items = items.filter(event=event)
    return items.exists()
