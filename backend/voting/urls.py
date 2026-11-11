from django.urls import path

from . import views

urlpatterns = [
    path('contests/<slug:slug>/', views.contest_detail, name='contest-detail'),
    path('contests/<slug:slug>/results/', views.contest_results, name='contest-results'),
    path('contests/<slug:slug>/ballots/', views.submit, name='ballot-submit'),
    path('contests/<slug:slug>/voter-session/', views.voter_session, name='voter-session'),
    path('contests/<slug:slug>/ballots/verify/', views.verify, name='ballot-verify'),
    path('admin/contests/<slug:slug>/stats/', views.admin_stats, name='admin-contest-stats'),
    path('admin/contests/<slug:slug>/export.csv', views.admin_export, name='admin-contest-export'),
    path('admin/contests/<slug:slug>/export.xlsx', views.admin_export_xlsx, name='admin-contest-export-xlsx'),
]
