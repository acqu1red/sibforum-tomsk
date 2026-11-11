import uuid
from io import BytesIO
from xml.sax.saxutils import escape

import qrcode
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from .models import RegistrationItem, Ticket

STATUS_LABELS = {
    'confirmed': 'Подтверждено',
    'pending_review': 'На рассмотрении',
    'approved': 'Одобрено',
    'rejected': 'Отклонено',
    'cancelled_by_user': 'Отменено участником',
    'cancelled_by_admin': 'Отменено администратором',
}
_font_registered = False


@transaction.atomic
def ensure_ticket(registration):
    eligible = registration.items.filter(
        status__in=(RegistrationItem.Status.CONFIRMED, RegistrationItem.Status.APPROVED),
    ).exists()
    ticket = Ticket.objects.select_for_update().filter(registration=registration).first()
    if not eligible:
        if ticket and ticket.status == Ticket.Status.ACTIVE:
            ticket.status = Ticket.Status.REVOKED
            ticket.revoked_at = timezone.now()
            ticket.save(update_fields=('status', 'revoked_at', 'updated_at'))
        return None
    if ticket and ticket.status == Ticket.Status.ACTIVE:
        return ticket
    if ticket:
        ticket.public_id = uuid.uuid4()
        ticket.status = Ticket.Status.ACTIVE
        ticket.version += 1
        ticket.issued_at = timezone.now()
        ticket.revoked_at = None
        ticket.save()
    else:
        ticket = Ticket.objects.create(registration=registration)
    return ticket


def checkin_url(ticket):
    return settings.ADMIN_SITE_URL + '/admin/check-in/' + str(ticket.public_id) + '/'


def ticket_qr_png(ticket):
    image = qrcode.make(checkin_url(ticket), box_size=10, border=2)
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


def register_pdf_font():
    global _font_registered
    if _font_registered:
        return
    pdfmetrics.registerFont(TTFont('ForumDejaVu', settings.PDF_FONT_PATH))
    _font_registered = True


def build_ticket_pdf(registration):
    register_pdf_font()
    ticket = registration.ticket
    participant = registration.participant
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title='Электронный билет — ' + participant.forum.title,
        author='Сибирский форум',
    )
    title = ParagraphStyle('title', fontName='ForumDejaVu', fontSize=17, leading=22, textColor=colors.HexColor('#071466'), spaceAfter=8)
    heading = ParagraphStyle('heading', fontName='ForumDejaVu', fontSize=12, leading=16, textColor=colors.HexColor('#3F4FB5'), spaceBefore=8, spaceAfter=5)
    body = ParagraphStyle('body', fontName='ForumDejaVu', fontSize=10, leading=15, alignment=TA_LEFT)
    small = ParagraphStyle('small', parent=body, fontSize=8, leading=12, textColor=colors.HexColor('#4A5070'))
    story = [
        Paragraph('Электронный билет', title),
        Paragraph(escape(participant.forum.title), heading),
        Paragraph(f"<b>{escape(participant.full_name)}</b><br/>{escape(participant.organization)}<br/>{escape(participant.position)}", body),
        Spacer(1, 4 * mm),
    ]
    qr = Image(BytesIO(ticket_qr_png(ticket)), width=47 * mm, height=47 * mm)
    details = [
        Paragraph(f"Номер заявки:<br/><b>{registration.id}</b>", body),
        Spacer(1, 3 * mm),
        Paragraph('QR предназначен для стойки регистрации. Он не открывает изменение вашей заявки.', small),
        Spacer(1, 3 * mm),
        Paragraph('Покажите код на экране телефона или распечатайте этот билет.', small),
    ]
    story.append(Table([[details, qr]], colWidths=[122 * mm, 48 * mm], style=TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#D9DCEB')),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6 * mm),
    ])))
    story.append(Paragraph('Ваши события', heading))
    for item in registration.items.select_related('event__day').prefetch_related('lot_links__lot'):
        event = item.event
        text = (
            f"<b>{escape(event.title)}</b><br/>"
            f"{escape(event.day.title)}, {event.start_time:%H:%M}–{event.end_time:%H:%M}<br/>"
            f"Статус: {STATUS_LABELS.get(item.status, item.status)}"
        )
        if event.is_paid:
            text += f"<br/>Стоимость: {event.price} ₽. {escape(event.payment_note)}"
        lots = list(item.lot_links.all())
        if lots:
            text += '<br/>Лоты: ' + escape(', '.join(str(link.lot.number) for link in lots))
        story.append(Paragraph(text, body))
        story.append(Spacer(1, 3 * mm))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(f'Билет сформирован: {timezone.localtime():%d.%m.%Y %H:%M} (Томск). Актуальная версия доступна по личной ссылке.', small))
    document.build(story)
    return buffer.getvalue()


def ticket_payload(ticket):
    if not ticket or ticket.status != Ticket.Status.ACTIVE:
        return None
    checkin = ticket.checkins.first()
    return {
        'id': str(ticket.public_id),
        'status': ticket.status,
        'version': ticket.version,
        'qr_path': f'/api/v1/tickets/{ticket.public_id}/qr.png',
        'pdf_path': f'/api/v1/tickets/{ticket.public_id}/ticket.pdf',
        'checkin_path': f'/admin/check-in/{ticket.public_id}/',
        'checked_in_at': checkin.created_at.isoformat() if checkin else None,
    }


def ticket_email_attachments(registration):
    ticket = Ticket.objects.filter(registration=registration, status=Ticket.Status.ACTIVE).first()
    if not ticket:
        return []
    return [
        (f'ticket-{ticket.public_id}.pdf', build_ticket_pdf(registration), 'application/pdf'),
        (f'ticket-{ticket.public_id}-qr.png', ticket_qr_png(ticket), 'image/png'),
    ]
