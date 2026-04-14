from django.urls import path

from . import views

urlpatterns = [
    path('', views.admin_tracks, name='admin-tracks'),
    path('status/', views.subtitle_generation_status, name='subtitle-generation-status'),
]
