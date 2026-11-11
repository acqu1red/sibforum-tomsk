import uuid
from urllib.parse import urlparse

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

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
@never_cache
@require_http_methods(['GET', 'POST'])
def scanner(request):
    matches, query = [], ''
    if request.method == 'POST' and 'search' in request.POST:
        query = str(request.POST.get('search', '')).strip()[:120]
        if len(query) < 3:
            messages.error(request, 'Введите минимум три символа имени, телефона или почты.')
        else:
            names = Q()
            for word in query.split():
                names &= (Q(registration__participant__last_name__icontains=word) |
                          Q(registration__participant__first_name__icontains=word) |
                          Q(registration__participant__middle_name__icontains=word))
            filters = names | Q(registration__participant__email__icontains=query)
            digits = ''.join(c for c in query if c.isdigit())
            if len(digits) >= 3:
                filters |= Q(registration__participant__phone__icontains=digits)
            if all(c in '0123456789abcdefABCDEF-' for c in query):
                filters |= Q(public_id__istartswith=query)
            matches = list(Ticket.objects.filter(filters, status=Ticket.Status.ACTIVE)
                           .select_related('registration__participant').prefetch_related('checkins')[:16])
            if not matches:
                messages.warning(request, 'Активный билет не найден. Проверьте данные или статус заявки в панели.')
    elif request.method == 'POST':
        try:
            public_id = ticket_code(request.POST.get('code'))
        except ValueError as error:
            messages.error(request, str(error))
        else:
            return redirect('check-in-ticket', public_id=public_id)
    return render(request, 'registrations/checkin.html', {'scanner': True, 'title': 'Встреча участников', 'matches': matches, 'query': query})


@staff_member_required
@permission_required('registrations.add_checkin', raise_exception=True)
@never_cache
@require_http_methods(['GET', 'POST'])
@transaction.atomic
def ticket_detail(request, public_id):
    qs = Ticket.objects.select_related('registration__participant__forum')
    if request.method == 'POST':
        qs = qs.select_for_update(of=('self',))
    ticket = qs.filter(public_id=public_id).first()
    if not ticket or ticket.status != Ticket.Status.ACTIVE:
        return render(request, 'registrations/checkin.html', {'scanner': False,
            'invalid_ticket': True, 'title': 'Билет отменён' if ticket else 'Билет не найден',
            'invalid_message': 'Этот билет больше не действует. Попросите участника открыть актуальный билет по личной ссылке.' if ticket else 'Проверьте QR-код или найдите участника по имени в сканере.'}, status=410 if ticket else 404)
    if request.method == 'POST' and request.POST.get('action') == 'confirm':
        if ticket.checkins.exists():
            messages.warning(request, 'Прибытие уже отмечено ранее.')
        else:
            try:
                with transaction.atomic():
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
