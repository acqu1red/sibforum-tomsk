from dataclasses import dataclass
from io import BytesIO

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from reportlab.lib.utils import simpleSplit
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from .admission import ticket_has_admission
from .attendance import scope
from .badge_docx import build_badge_docx, DOCX_CONTENT_TYPE
from .models import Ticket


BADGE_SIZE = (70 * mm, 50 * mm)
BADGE_FONT = 'ForumBadgeBold'
BADGE_ORGANIZATION_FONT = 'ForumBadgeRegular'
BADGE_TEXT_WIDTH = BADGE_SIZE[0] - 6 * mm
BADGE_LINE_HEIGHT = 1.1


@dataclass(frozen=True)
class BadgeLine:
    text: str
    size: float
    bold: bool = True
    space_before: float = 0

    @property
    def font(self):
        return BADGE_FONT if self.bold else BADGE_ORGANIZATION_FONT


def fit_badge_line(text, max_size, space_before=0):
    unit_width = pdfmetrics.stringWidth(text, BADGE_FONT, 1)
    return BadgeLine(text, min(max_size, BADGE_TEXT_WIDTH / unit_width) if unit_width else max_size,
                     space_before=space_before)


def badge_lines(participant):
    if BADGE_FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(BADGE_FONT, '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'))
    if BADGE_ORGANIZATION_FONT not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(BADGE_ORGANIZATION_FONT, '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'))

    surname = ' '.join(participant.last_name.split()).upper()
    first_name = ' '.join(participant.first_name.split()).title()
    lines = []
    organization = ' '.join(participant.organization.split())
    if organization:
        size = 11
        words = simpleSplit(organization, BADGE_ORGANIZATION_FONT, size, BADGE_TEXT_WIDTH)
        while len(words) > 3:
            size -= 0.5
            words = simpleSplit(organization, BADGE_ORGANIZATION_FONT, size, BADGE_TEXT_WIDTH)
        widest = max(pdfmetrics.stringWidth(line, BADGE_ORGANIZATION_FONT, size) for line in words)
        if widest > BADGE_TEXT_WIDTH:
            size *= BADGE_TEXT_WIDTH / widest
        lines.extend(BadgeLine(line, size, bold=False) for line in words)

    name_spacing = 4 * mm if lines else 0
    names = [name for name in (surname, first_name) if name]
    combined = fit_badge_line(' '.join(names), 36, name_spacing)
    if len(names) == 2 and combined.size < 26:
        lines.append(fit_badge_line(surname, 37, name_spacing))
        lines.append(fit_badge_line(first_name, 31, 1.5 * mm))
    elif names:
        lines.append(combined)
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
    text_height = sum(line.size * BADGE_LINE_HEIGHT + line.space_before for line in lines)
    top = (height + text_height) / 2
    for line in lines:
        top -= line.space_before
        line_height = line.size * BADGE_LINE_HEIGHT
        ascent, descent = pdfmetrics.getAscentDescent(line.font, line.size)
        baseline = top - (line_height + ascent + descent) / 2
        pdf.setFont(line.font, line.size)
        pdf.drawCentredString(width / 2, baseline, line.text)
        top -= line_height
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


@staff_member_required
@permission_required('registrations.add_checkin', raise_exception=True)
@never_cache
@require_GET
def attendee_badge(request, public_id, file_format='pdf'):
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
    if file_format == 'docx':
        response = HttpResponse(build_badge_docx(lines, BADGE_SIZE, BADGE_LINE_HEIGHT), content_type=DOCX_CONTENT_TYPE)
        response['Content-Disposition'] = f'attachment; filename="badge-{str(public_id)[:8]}.docx"'
        return response
    if request.GET.get('print') == '1':
        return render(request, 'registrations/badge_print.html', {
            'badge_lines': lines,
            'scope_query': context['scope_query'],
            'ticket_id': ticket.public_id,
        })
    response = HttpResponse(build_badge_pdf(lines), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="badge-{str(public_id)[:8]}.pdf"'
    return response
