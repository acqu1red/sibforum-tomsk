from django.urls import path

from . import checkin, exports

urlpatterns = [
    path('exports/', exports.export_page, name='registration-export-page'),
    path('check-in/', checkin.scanner, name='check-in-scanner'),
    path('check-in/<uuid:public_id>/', checkin.ticket_detail, name='check-in-ticket'),
]
