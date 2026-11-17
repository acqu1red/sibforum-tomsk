from django.db.models import Q
from .models import RegistrationItem


def eligible_items(items):
    return items.filter(status__in=(RegistrationItem.Status.CONFIRMED, RegistrationItem.Status.APPROVED)).filter(
        Q(event__is_paid=False) | Q(payment_status=RegistrationItem.PaymentStatus.CONFIRMED))
