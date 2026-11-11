from django.urls import path

from . import exports, views

urlpatterns = [
    path('registrations/submit/', views.submit, name='registration-submit'),
    path('registrations/verify/', views.verify, name='registration-verify'),
    path('registration/', views.personal_registration, name='personal-registration'),
    path('tickets/<uuid:public_id>/qr.png', views.ticket_qr, name='ticket-qr'),
    path('tickets/<uuid:public_id>/ticket.pdf', views.ticket_pdf, name='ticket-pdf'),
    path('admin/registrations/', views.admin_registrations, name='admin-registrations'),
    path('admin/registrations/export.<str:format>', exports.registration_export, name='admin-registration-export'),
    path('admin/registration-items/<uuid:item_id>/decision/', views.admin_decision, name='admin-decision'),
]
