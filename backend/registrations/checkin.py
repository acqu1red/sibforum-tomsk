import uuid
from urllib.parse import urlparse

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from .models import CheckIn, Ticket


def ticket_code(value):
    value = str(value or '').strip()
    if '://' in value:
        value = urlparse(value).path.rstrip('/').split('/')[-1]
    try:
        return uuid.UUID(value)
    except (ValueError, TypeError, AttributeError):
        raise ValueError('Некорректный код билета.')


@staff_member_required
@permission_required('registrations.add_checkin', raise_exception=True)
def scanner(request):
    if request.method == 'POST':
        try:
            public_id = ticket_code(request.POST.get('code'))
        except ValueError as error:
            messages.error(request, str(error))
        else:
            return redirect('check-in-ticket', public_id=public_id)
    return render(request, 'registrations/checkin.html', {'scanner': True, 'title': 'Сканер участников'})


@staff_member_required
@permission_required('registrations.add_checkin', raise_exception=True)
def ticket_detail(request, public_id):
    ticket = get_object_or_404(
        Ticket.objects.select_related('registration__participant__forum'),
        public_id=public_id,
        status=Ticket.Status.ACTIVE,
    )
    if request.method == 'POST' and request.POST.get('action') == 'confirm':
        if ticket.checkins.exists():
            messages.warning(request, 'Прибытие уже отмечено ранее.')
        else:
            try:
                CheckIn.objects.create(ticket=ticket, admin_user=request.user)
                messages.success(request, 'Прибытие участника подтверждено.')
            except IntegrityError:
                messages.warning(request, 'Прибытие уже отмечено другим сотрудником.')
        return redirect('check-in-ticket', public_id=public_id)
    registration = ticket.registration
    return render(request, 'registrations/checkin.html', {
        'scanner': False,
        'ticket': ticket,
        'registration': registration,
        'participant': registration.participant,
        'items': registration.items.select_related('event__day').prefetch_related('lot_links__lot'),
        'checkin': ticket.checkins.select_related('admin_user').first(),
        'title': 'Билет участника',
    })
