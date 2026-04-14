from pathlib import Path

from django import forms
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render

from .services import (
    SUPPORTED_AUDIO_EXTENSIONS,
    delete_track_files,
    get_track_generation_error,
    get_track,
    get_track_eta_seconds,
    is_track_generating,
    list_tracks,
    save_uploaded_track,
    start_track_generation,
)


class TrackUploadForm(forms.Form):
    title = forms.CharField(max_length=120, required=False)
    audio_file = forms.FileField()

    def clean_audio_file(self):
        audio_file = self.cleaned_data['audio_file']
        extension = Path(audio_file.name).suffix.lower()
        if extension not in SUPPORTED_AUDIO_EXTENSIONS:
            raise forms.ValidationError(
                f"Unsupported audio format. Allowed: {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}"
            )
        return audio_file


@staff_member_required
def subtitle_generation_status(request):
    tracks = list_tracks()
    status_by_track = {
        track['slug']: {
            'is_generating': is_track_generating(track['slug']),
            'has_subtitles': track['has_subtitles'],
            'eta_seconds': get_track_eta_seconds(track['slug']),
            'error': get_track_generation_error(track['slug']),
        }
        for track in tracks
    }
    return JsonResponse({'tracks': status_by_track})


@staff_member_required
def admin_tracks(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'upload')
        if action == 'generate_subtitles':
            track_slug = request.POST.get('track_slug', '').strip()
            if not track_slug:
                return HttpResponseBadRequest('Missing track slug')

            track = get_track(track_slug, list_tracks())
            if not track:
                return HttpResponseBadRequest('Unknown track slug')

            start_track_generation(track)
            return redirect('admin-tracks')

        if action == 'delete':
            track_slug = request.POST.get('track_slug', '').strip()
            if not track_slug:
                return HttpResponseBadRequest('Missing track slug')

            delete_track_files(track_slug)
            return redirect('admin-tracks')

        form = TrackUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_track = save_uploaded_track(form.cleaned_data['audio_file'], form.cleaned_data['title'])
            start_track_generation(uploaded_track)
            return redirect('admin-tracks')
    else:
        form = TrackUploadForm()

    tracks = list_tracks()
    return render(
        request,
        'podcast_management/admin_tracks.html',
        {
            'form': form,
            'tracks': tracks,
        },
    )
