from django.urls import include, path


app_name = 'podcast'

urlpatterns = [
    path('manage', include(('podcast_management.urls', 'podcast_management'), namespace='podcast_management')),
    path('', include(('player.urls', 'player'), namespace='player')),
]
