from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='player-index'),
    path('<slug:slug>/', views.index, name='player-episode'),
    path('api/subtitles/', views.subtitle_segments, name='subtitle-segments'),
]
