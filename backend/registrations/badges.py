from dataclasses import dataclass
from io import BytesIO
from math import floor

from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import permission_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib.utils import simpleSplit
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from .admission import ticket_has_admission
from .attendance import scope
from .badge_docx import build_badge_docx, DOCX_CONTENT_TYPE
from .badge_fonts import BADGE_FONTS
from .models import Ticket


BADGE_SIZE = (70 * mm, 50 * mm)
BADGE_TEXT_WIDTH = BADGE_SIZE[0] - 6 * mm
BADGE_LINE_HEIGHT = 1.05
NAME_SIZE = 24
ORGANIZATION_SIZE = 14


@dataclass(frozen=True)
class BadgeLine:
    text: str
    size: float
    bold: bool = True
    space_before: float = 0
    width_percent: int = 100

    @property
    def font(self):
        return BADGE_FONTS[self.bold][0]


def fit_badge_line(text, size, *, bold=True, space_before=0):
    width = pdfmetrics.stringWidth(text, BADGE_FONTS[bold][0], size)
    width_percent = min(100, max(1, floor(100 * BADGE_TEXT_WIDTH / width))) if width else 100
    return BadgeLine(text, size, bold, space_before, width_percent)


def badge_lines(participant):
    for font, path in BADGE_FONTS.values():
        if font not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(font, str(path)))

    surname = ' '.join(participant.last_name.split()).title()
    first_name = ' '.join(participant.first_name.split()).title()
    lines = []
    organization = ' '.join(participant.organization.split())
    if organization:
        width = BADGE_TEXT_WIDTH
        organization_font = BADGE_FONTS[False][0]
        organization_lines = simpleSplit(organization, organization_font, ORGANIZATION_SIZE, width)
        while len(organization_lines) > 4:
            width *= 1.1
            organization_lines = simpleSplit(organization, organization_font, ORGANIZATION_SIZE, width)
        lines.extend(fit_badge_line(line, ORGANIZATION_SIZE, bold=False) for line in organization_lines)

    name_spacing = 2.5 * mm if lines else 0
    names = [name for name in (first_name, surname) if name]
    combined = fit_badge_line(' '.join(names), NAME_SIZE, space_before=name_spacing)
    if len(names) == 2 and combined.width_percent < 100:
        lines.append(fit_badge_line(first_name, NAME_SIZE, space_before=name_spacing))
        lines.append(fit_badge_line(surname, NAME_SIZE, space_before=mm))
    elif names:
        lines.append(combined)
    return lines


def badge_baselines(lines):
    text_height = sum(line.size * BADGE_LINE_HEIGHT + line.space_before for line in lines)
    top = (BADGE_SIZE[1] + text_height) / 2
    for line in lines:
        top -= line.space_before
        line_height = line.size * BADGE_LINE_HEIGHT
        ascent, descent = pdfmetrics.getAscentDescent(line.font, line.size)
        yield line, top - (line_height + ascent + descent) / 2
        top -= line_height


def build_badge_pdf(lines):
    width, height = BADGE_SIZE
    buffer = BytesIO()
    pdf = Canvas(buffer, pagesize=BADGE_SIZE)
    pdf.setTitle('Бейдж участника')
    pdf.setViewerPreference('PrintScaling', 'None')
    pdf.setFillColorRGB(1, 1, 1)
    pdf.rect(0, 0, width, height, fill=1, stroke=0)
    pdf.setFillColorRGB(0, 0, 0)
    for line, baseline in badge_baselines(lines):
        text_width = pdfmetrics.stringWidth(line.text, line.font, line.size) * line.width_percent / 100
        text = pdf.beginText((width - text_width) / 2, baseline)
        text.setFont(line.font, line.size)
        text.setHorizScale(line.width_percent)
        text.textOut(line.text)
        pdf.drawText(text)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def build_badge_print_image(lines):
    # Render the same font server-side for browsers that don't have Times New Roman.
    scale = 600 / 72
    width, height = (round(points * scale) for points in BADGE_SIZE)
    image = Image.new('L', (width, height), 255)
    for line, baseline in badge_baselines(lines):
        font = ImageFont.truetype(str(BADGE_FONTS[line.bold][1]), round(line.size * scale))
        left, top, right, bottom = font.getbbox(line.text, anchor='ls')
        mask = Image.new('L', (max(1, right - left), max(1, bottom - top)))
        ImageDraw.Draw(mask).text((-left, -top), line.text, font=font, fill=255, anchor='ls')
        scaled_width = max(1, round(mask.width * line.width_percent / 100))
        if scaled_width != mask.width:
            mask = mask.resize((scaled_width, mask.height), Image.Resampling.LANCZOS)
        image.paste(0, ((width - mask.width) // 2, round(height - baseline * scale + top)), mask)
    buffer = BytesIO()
    image.save(buffer, format='PNG', dpi=(600, 600))
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
    if file_format == 'png':
        return HttpResponse(build_badge_print_image(lines), content_type='image/png')
    if file_format == 'docx':
        response = HttpResponse(build_badge_docx(lines, BADGE_SIZE, BADGE_LINE_HEIGHT), content_type=DOCX_CONTENT_TYPE)
        response['Content-Disposition'] = f'attachment; filename="badge-{str(public_id)[:8]}.docx"'
        return response
    if request.GET.get('print') == '1':
        return render(request, 'registrations/badge_print.html', {
            'scope_query': context['scope_query'],
            'ticket_id': ticket.public_id,
        })
    response = HttpResponse(build_badge_pdf(lines), content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="badge-{str(public_id)[:8]}.pdf"'
    return response
