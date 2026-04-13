from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='player-index'),
    path('api/subtitles/', views.subtitle_segments, name='subtitle-segments'),
    path('manage/tracks/', views.admin_tracks, name='admin-tracks'),
    path('manage/tracks/status/', views.subtitle_generation_status, name='subtitle-generation-status'),
]
