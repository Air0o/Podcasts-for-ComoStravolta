from django.http import Http404, JsonResponse
from django.shortcuts import render

from podcast_management.services import ensure_subtitles, get_track, list_tracks, load_track_segments


def index(request):
	tracks = list_tracks()
	selected_slug = request.GET.get('track')
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

	ensure_subtitles(track)

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
