from io import BytesIO

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfgen.canvas import Canvas

from .admission import ticket_has_admission
from .attendance import scope
from .models import Ticket
from .tickets import register_pdf_font


BADGE_SIZE = (50 * mm, 70 * mm)
BADGE_FONT = 'ForumDejaVu'


def badge_name(participant):
    return ' '.join(f'{participant.first_name} {participant.last_name}'.split())


def badge_font_size(name):
    register_pdf_font()
    natural_width = pdfmetrics.stringWidth(name, BADGE_FONT, 12)
    return min(12, 12 * (BADGE_SIZE[0] - 8 * mm) / natural_width) if natural_width else 12


def build_badge_pdf(name):
    size = badge_font_size(name)
    width, height = BADGE_SIZE
    buffer = BytesIO()
    pdf = Canvas(buffer, pagesize=BADGE_SIZE)
    pdf.setTitle('Бейдж участника')
    pdf.setViewerPreference('PrintScaling', 'None')
    pdf.setFillColorRGB(1, 1, 1)
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.setFont(BADGE_FONT, size)
    ascent, descent = pdfmetrics.getAscentDescent(BADGE_FONT, size)
    pdf.drawCentredString(width / 2, (height - ascent - descent) / 2, name)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


@staff_member_required
@permission_required('registrations.add_checkin', raise_exception=True)
@never_cache
@require_GET
def attendee_badge(request, public_id):
    context = scope(request)
    ticket = get_object_or_404(
        Ticket.objects.select_related('registration__participant'),
        public_id=public_id,
        status=Ticket.Status.ACTIVE,
        registration__participant__forum=context['forum'],
    )
    event = context['selected_event']
    if not ticket_has_admission(ticket, event) and not ticket.checkins.filter(event=event).exists():
        raise Http404('Для выбранного входа нет допуска')
    name = badge_name(ticket.registration.participant)
    if request.GET.get('print') == '1':
        return render(request, 'registrations/badge_print.html', {
            'name': name,
            'font_size': badge_font_size(name),
            'scope_query': context['scope_query'],
        })
    response = HttpResponse(build_badge_pdf(name), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="badge-{str(public_id)[:8]}.pdf"'
    return response
