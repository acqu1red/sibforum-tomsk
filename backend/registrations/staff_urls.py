from django.urls import path

from . import assistance, checkin, exports

urlpatterns = [
    path('registration-help/<uuid:registration_id>/', assistance.participant_help, name='registration-assistance'),
    path('registration-help/<uuid:registration_id>/resend/', assistance.resend, name='registration-resend'),
    path('registration-help/<uuid:registration_id>/ticket/qr.png', assistance.download_qr, name='registration-staff-qr'),
    path('registration-help/<uuid:registration_id>/ticket/ticket.pdf', assistance.download_pdf, name='registration-staff-pdf'),
    path('exports/', exports.export_page, name='registration-export-page'),
    path('check-in/', checkin.scanner, name='check-in-scanner'),
    path('check-in/<uuid:public_id>/', checkin.ticket_detail, name='check-in-ticket'),
]
