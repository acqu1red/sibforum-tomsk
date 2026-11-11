from django.urls import path

from . import views

urlpatterns = [
    path('admin/2fa/setup/', views.setup, name='two-factor-setup'),
    path('admin/2fa/verify/', views.verify, name='two-factor-verify'),
]
