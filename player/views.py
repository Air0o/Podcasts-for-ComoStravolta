from django.http import Http404, JsonResponse
from django.shortcuts import render

from podcast_management.services import get_track, list_tracks, load_track_segments


def index(request, slug=None):
	tracks = list_tracks()
	selected_slug = slug or request.GET.get('track')
	current_track = get_track(selected_slug, tracks)
	context = {
		'tracks': [{'slug': t['slug'], 'title': t['title'], 'audio_url': t['audio_url']} for t in tracks],
		'current_track': current_track,
	}
	return render(request, 'player/index.html', context)


def subtitle_segments(request):
	tracks = list_tracks()
	track = get_track(request.GET.get('track'), tracks)
	if not track:
		raise Http404('No subtitle tracks are available')
	if not track.get('has_subtitles'):
		raise Http404('No aligned subtitles are available for this track')

	segments = load_track_segments(track)
	return JsonResponse(
		{
			'track': {
				'slug': track['slug'],
				'title': track['title'],
				'audio_url': track['audio_url'],
			},
			'segments': segments,
		}
	)
