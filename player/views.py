from pathlib import Path
from threading import Lock, Thread
from time import monotonic

from django import forms
from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import redirect, render
from django.utils.text import slugify

from subtitles import get_audio_duration_seconds, get_subtitles, load_segments_json, save_segments_json


SUPPORTED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".ogg", ".flac"}
DEFAULT_WHISPER_MODEL = "medium"
_GENERATING_TRACKS: set[str] = set()
_GENERATING_TRACKS_LOCK = Lock()
_MINIMUM_ETA_OVERHEAD_SECONDS = 1.0
_DEFAULT_SECONDS_PER_AUDIO_SECOND = 0.55
_MIN_SECONDS_PER_AUDIO_SECOND = 0.15
_MAX_SECONDS_PER_AUDIO_SECOND = 1.25
_seconds_per_audio_second = _DEFAULT_SECONDS_PER_AUDIO_SECOND
_GENERATION_TIMINGS: dict[str, dict[str, float]] = {}


class TrackUploadForm(forms.Form):
	title = forms.CharField(max_length=120, required=False)
	audio_file = forms.FileField()

	def clean_audio_file(self):
		audio_file = self.cleaned_data["audio_file"]
		extension = Path(audio_file.name).suffix.lower()
		if extension not in SUPPORTED_AUDIO_EXTENSIONS:
			raise forms.ValidationError(
				f"Unsupported audio format. Allowed: {', '.join(sorted(SUPPORTED_AUDIO_EXTENSIONS))}"
			)
		return audio_file


def _audio_directory() -> Path:
	return Path(settings.MEDIA_ROOT) / "audio"


def _subtitle_directory() -> Path:
	return Path(settings.MEDIA_ROOT) / "subtitles"


def _unique_audio_path(base_slug: str, extension: str, audio_dir: Path) -> Path:
	candidate = audio_dir / f"{base_slug}{extension}"
	index = 2
	while candidate.exists():
		candidate = audio_dir / f"{base_slug}-{index}{extension}"
		index += 1
	return candidate


def _track_payload(audio_file: Path) -> dict:
	subtitle_dir = _subtitle_directory()
	subtitle_dir.mkdir(parents=True, exist_ok=True)

	slug = audio_file.stem
	subtitle_file = subtitle_dir / f"{slug}.json"
	return {
		"slug": slug,
		"title": slug.replace("_", " ").replace("-", " ").title(),
		"audio_url": f"{settings.MEDIA_URL}audio/{audio_file.name}",
		"audio_file": str(audio_file),
		"subtitle_file": str(subtitle_file),
		"has_subtitles": subtitle_file.exists(),
	}


def _save_uploaded_track(uploaded_file, title: str) -> dict:
	audio_dir = _audio_directory()
	audio_dir.mkdir(parents=True, exist_ok=True)

	extension = Path(uploaded_file.name).suffix.lower()
	requested_slug = slugify(title) if title else ""
	name_slug = slugify(Path(uploaded_file.name).stem)
	base_slug = requested_slug or name_slug or "track"

	destination = _unique_audio_path(base_slug, extension, audio_dir)
	with destination.open("wb+") as target:
		for chunk in uploaded_file.chunks():
			target.write(chunk)

	return _track_payload(destination)


def _delete_track_files(track_slug: str) -> bool:
	audio_dir = _audio_directory()
	subtitle_dir = _subtitle_directory()

	deleted = False
	for extension in SUPPORTED_AUDIO_EXTENSIONS:
		audio_file = audio_dir / f"{track_slug}{extension}"
		if audio_file.exists():
			audio_file.unlink()
			deleted = True

	subtitle_file = subtitle_dir / f"{track_slug}.json"
	if subtitle_file.exists():
		subtitle_file.unlink()
		deleted = True

	return deleted


def _list_tracks() -> list[dict]:
	audio_dir = _audio_directory()
	subtitle_dir = _subtitle_directory()

	if not audio_dir.exists():
		return []

	subtitle_dir.mkdir(parents=True, exist_ok=True)

	tracks = []
	for audio_file in sorted(audio_dir.iterdir()):
		if not audio_file.is_file() or audio_file.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
			continue

		tracks.append(_track_payload(audio_file))
	return tracks


def _ensure_subtitles(track: dict) -> None:
	subtitle_path = Path(track["subtitle_file"])
	if subtitle_path.exists():
		return

	segments = get_subtitles(track["audio_file"], model_name=DEFAULT_WHISPER_MODEL)
	save_segments_json(segments, subtitle_path)


def _is_track_generating(track_slug: str) -> bool:
	with _GENERATING_TRACKS_LOCK:
		return track_slug in _GENERATING_TRACKS


def _get_track_eta_seconds(track_slug: str) -> float | None:
	with _GENERATING_TRACKS_LOCK:
		timing = _GENERATION_TIMINGS.get(track_slug)
		if not timing:
			return None

		elapsed = monotonic() - timing["started_at"]
		bias_reduction = min(0.25, elapsed / 80.0)
		adjusted_total = timing["estimated_total_seconds"] * (1.0 - bias_reduction)
		remaining = adjusted_total - elapsed

		return max(0.0, remaining)


def _start_track_generation(track: dict) -> bool:
	global _seconds_per_audio_second

	track_slug = track["slug"]
	audio_duration_seconds = 0.0
	try:
		audio_duration_seconds = get_audio_duration_seconds(track["audio_file"])
	except Exception:
		audio_duration_seconds = 0.0

	estimated_total_seconds = _MINIMUM_ETA_OVERHEAD_SECONDS + (
		audio_duration_seconds * _seconds_per_audio_second
	)
	started_at = monotonic()

	with _GENERATING_TRACKS_LOCK:
		if track_slug in _GENERATING_TRACKS:
			return False
		_GENERATING_TRACKS.add(track_slug)
		_GENERATION_TIMINGS[track_slug] = {
			"started_at": started_at,
			"estimated_total_seconds": estimated_total_seconds,
			"audio_duration_seconds": audio_duration_seconds,
		}

	def _run_generation() -> None:
		global _seconds_per_audio_second
		started = monotonic()
		try:
			segments = get_subtitles(track["audio_file"], model_name=DEFAULT_WHISPER_MODEL)
			save_segments_json(segments, Path(track["subtitle_file"]))
		finally:
			with _GENERATING_TRACKS_LOCK:
				timing = _GENERATION_TIMINGS.pop(track_slug, None)
				if timing:
					audio_seconds = timing.get("audio_duration_seconds", 0.0)
					if audio_seconds > 0.0:
						actual_ratio = (monotonic() - started) / audio_seconds
						actual_ratio = max(
							_MIN_SECONDS_PER_AUDIO_SECOND,
							min(_MAX_SECONDS_PER_AUDIO_SECOND, actual_ratio),
						)
						_seconds_per_audio_second = (
							(_seconds_per_audio_second * 0.45)
							+ (actual_ratio * 0.55)
						)
				_GENERATING_TRACKS.discard(track_slug)

	Thread(target=_run_generation, daemon=True).start()
	return True


def _get_track(track_slug: str | None, tracks: list[dict]) -> dict | None:
	if not tracks:
		return None

	if track_slug:
		for track in tracks:
			if track["slug"] == track_slug:
				return track
	return tracks[0]


def index(request):
	tracks = _list_tracks()
	selected_slug = request.GET.get("track")
	current_track = _get_track(selected_slug, tracks)
	context = {
		"tracks": [{"slug": t["slug"], "title": t["title"], "audio_url": t["audio_url"]} for t in tracks],
		"current_track": current_track,
	}
	return render(request, "player/index.html", context)


def subtitle_segments(request):
	tracks = _list_tracks()
	track = _get_track(request.GET.get("track"), tracks)
	if not track:
		raise Http404("No subtitle tracks are available")

	_ensure_subtitles(track)

	segments = load_segments_json(Path(track["subtitle_file"]))
	return JsonResponse(
		{
			"track": {
				"slug": track["slug"],
				"title": track["title"],
				"audio_url": track["audio_url"],
			},
			"segments": segments,
		}
	)


@staff_member_required
def subtitle_generation_status(request):
	tracks = _list_tracks()
	status_by_track = {
		track["slug"]: {
			"is_generating": _is_track_generating(track["slug"]),
			"has_subtitles": track["has_subtitles"],
			"eta_seconds": _get_track_eta_seconds(track["slug"]),
		}
		for track in tracks
	}
	return JsonResponse({"tracks": status_by_track})


@staff_member_required
def admin_tracks(request):
	if request.method == "POST":
		action = request.POST.get("action", "upload")
		if action == "generate_subtitles":
			track_slug = request.POST.get("track_slug", "").strip()
			if not track_slug:
				return HttpResponseBadRequest("Missing track slug")

			track = _get_track(track_slug, _list_tracks())
			if not track:
				return HttpResponseBadRequest("Unknown track slug")

			_start_track_generation(track)
			return redirect("admin-tracks")

		if action == "delete":
			track_slug = request.POST.get("track_slug", "").strip()
			if not track_slug:
				return HttpResponseBadRequest("Missing track slug")

			_delete_track_files(track_slug)
			return redirect("admin-tracks")

		form = TrackUploadForm(request.POST, request.FILES)
		if form.is_valid():
			uploaded_track = _save_uploaded_track(form.cleaned_data["audio_file"], form.cleaned_data["title"])
			_start_track_generation(uploaded_track)
			return redirect("admin-tracks")
	else:
		form = TrackUploadForm()

	tracks = _list_tracks()
	return render(
		request,
		"player/admin_tracks.html",
		{
			"form": form,
			"tracks": tracks,
		},
	)
