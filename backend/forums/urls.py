from django.urls import path

from . import views

urlpatterns = [
    path('health/', views.health, name='health'),
    path('public-config/', views.public_config, name='public-config'),
    path('forums/', views.forum_list, name='forum-list'),
    path('forums/<slug:slug>/program/', views.forum_program, name='forum-program'),
]
