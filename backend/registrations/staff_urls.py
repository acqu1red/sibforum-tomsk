from django.urls import path

from . import assistance, badges, checkin, exports, attendance
from voting.exports import voting_export

urlpatterns = [
    path('attendance/', attendance.attendance, name='check-in-attendance'),
    path('registration-help/<uuid:registration_id>/', assistance.participant_help, name='registration-assistance'),
    path('registration-help/<uuid:registration_id>/resend/', assistance.resend, name='registration-resend'),
    path('registration-help/<uuid:registration_id>/ticket/qr.png', assistance.download_qr, name='registration-staff-qr'),
    path('registration-help/<uuid:registration_id>/ticket/ticket.pdf', assistance.download_pdf, name='registration-staff-pdf'),
    path('exports/', exports.export_page, name='registration-export-page'),
    path('exports/registrations.<str:format>', exports.registration_export, name='staff-registration-export'),
    path('exports/voting/<slug:slug>.<str:format>', voting_export, name='staff-voting-export'),
    path('check-in/', checkin.scanner, name='check-in-scanner'),
    path('check-in/<uuid:public_id>/badge.pdf', badges.attendee_badge, name='check-in-badge'),
    path('check-in/<uuid:public_id>/badge.docx', badges.attendee_badge, {'file_format': 'docx'}, name='check-in-badge-word'),
    path('check-in/<uuid:public_id>/badge.png', badges.attendee_badge, {'file_format': 'png'}, name='check-in-badge-image'),
    path('check-in/<uuid:public_id>/', checkin.ticket_detail, name='check-in-ticket'),
]
