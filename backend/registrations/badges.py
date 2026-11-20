from dataclasses import dataclass
from io import BytesIO

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from .admission import ticket_has_admission
from .attendance import scope
from .models import Ticket


BADGE_SIZE = (70 * mm, 50 * mm)
BADGE_FONT = 'ForumBadgeBold'
BADGE_TEXT_WIDTH = BADGE_SIZE[0] - 6 * mm
BADGE_LINE_GAP = 2 * mm
BADGE_LINE_HEIGHT = 1.1


@dataclass(frozen=True)
class BadgeLine:
    text: str
    size: float


def fit_badge_line(text, max_size):
    unit_width = pdfmetrics.stringWidth(text, BADGE_FONT, 1)
    return BadgeLine(text, min(max_size, BADGE_TEXT_WIDTH / unit_width) if unit_width else max_size)


def badge_lines(participant):
    if BADGE_FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(BADGE_FONT, '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))

    surname = ' '.join(participant.last_name.split()).upper()
    given_names = [' '.join(value.split()).title() for value in (participant.first_name, participant.middle_name) if value.strip()]
    lines = [fit_badge_line(surname, 48)] if surname else []
    if given_names:
        given_line = fit_badge_line(' '.join(given_names), 34)
        if len(given_names) == 2 and given_line.size < 13:
            lines.extend(fit_badge_line(value, 29) for value in given_names)
        else:
            lines.append(given_line)
    return lines


def build_badge_pdf(lines):
    width, height = BADGE_SIZE
    buffer = BytesIO()
    pdf = Canvas(buffer, pagesize=BADGE_SIZE)
    pdf.setTitle('Бейдж участника')
    pdf.setViewerPreference('PrintScaling', 'None')
    pdf.setFillColorRGB(1, 1, 1)
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setFillColorRGB(0, 0, 0)
    text_height = sum(line.size * BADGE_LINE_HEIGHT for line in lines)
    text_height += BADGE_LINE_GAP * max(0, len(lines) - 1)
    top = (height + text_height) / 2
    for line in lines:
        line_height = line.size * BADGE_LINE_HEIGHT
        ascent, descent = pdfmetrics.getAscentDescent(BADGE_FONT, line.size)
        baseline = top - (line_height + ascent + descent) / 2
        pdf.setFont(BADGE_FONT, line.size)
        pdf.drawCentredString(width / 2, baseline, line.text)
        top -= line_height + BADGE_LINE_GAP
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
    lines = badge_lines(ticket.registration.participant)
    if request.GET.get('print') == '1':
        return render(request, 'registrations/badge_print.html', {
            'badge_lines': lines,
            'scope_query': context['scope_query'],
        })
    response = HttpResponse(build_badge_pdf(lines), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="badge-{str(public_id)[:8]}.pdf"'
    return response
