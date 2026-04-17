from pathlib import Path
from threading import Lock, Thread
from time import monotonic
import logging

from django.conf import settings
from django.utils.text import slugify

from subtitles import get_audio_duration_seconds, get_subtitles, load_segments_json, save_segments_json


SUPPORTED_AUDIO_EXTENSIONS = {'.mp3', '.wav', '.m4a', '.ogg', '.flac'}
_GENERATING_TRACKS: set[str] = set()
_GENERATING_TRACKS_LOCK = Lock()
_MINIMUM_ETA_OVERHEAD_SECONDS = 1.0
_DEFAULT_SECONDS_PER_AUDIO_SECOND = 2
_MIN_SECONDS_PER_AUDIO_SECOND = 0.5
_MAX_SECONDS_PER_AUDIO_SECOND = 3
_seconds_per_audio_second = _DEFAULT_SECONDS_PER_AUDIO_SECOND
_GENERATION_TIMINGS: dict[str, dict[str, float]] = {}
_GENERATION_ERRORS: dict[str, str] = {}
logger = logging.getLogger(__name__)


def audio_directory() -> Path:
    return Path(settings.MEDIA_ROOT) / 'audio'


def subtitle_directory() -> Path:
    return Path(settings.MEDIA_ROOT) / 'subtitles'


def unique_audio_path(base_slug: str, extension: str, audio_dir: Path) -> Path:
    candidate = audio_dir / f'{base_slug}{extension}'
    index = 2
    while candidate.exists():
        candidate = audio_dir / f'{base_slug}-{index}{extension}'
        index += 1
    return candidate


def track_payload(audio_file: Path) -> dict:
    subtitle_dir = subtitle_directory()
    subtitle_dir.mkdir(parents=True, exist_ok=True)

    slug = audio_file.stem
    subtitle_file = subtitle_dir / f'{slug}.json'
    return {
        'slug': slug,
        'title': slug.replace('_', ' ').replace('-', ' ').title(),
        'audio_url': f"{settings.MEDIA_URL}audio/{audio_file.name}",
        'audio_file': str(audio_file),
        'subtitle_file': str(subtitle_file),
        'has_subtitles': subtitle_file.exists(),
    }


def save_uploaded_track(uploaded_file, title: str) -> dict:
    audio_dir = audio_directory()
    audio_dir.mkdir(parents=True, exist_ok=True)

    extension = Path(uploaded_file.name).suffix.lower()
    requested_slug = slugify(title) if title else ''
    name_slug = slugify(Path(uploaded_file.name).stem)
    base_slug = requested_slug or name_slug or 'track'

    destination = unique_audio_path(base_slug, extension, audio_dir)
    with destination.open('wb+') as target:
        for chunk in uploaded_file.chunks():
            target.write(chunk)

    return track_payload(destination)


def delete_track_files(track_slug: str) -> bool:
    audio_dir = audio_directory()
    subtitle_dir = subtitle_directory()

    deleted = False
    for extension in SUPPORTED_AUDIO_EXTENSIONS:
        audio_file = audio_dir / f'{track_slug}{extension}'
        if audio_file.exists():
            audio_file.unlink()
            deleted = True

    subtitle_file = subtitle_dir / f'{track_slug}.json'
    if subtitle_file.exists():
        subtitle_file.unlink()
        deleted = True

    return deleted


def list_tracks() -> list[dict]:
    audio_dir = audio_directory()
    subtitle_directory().mkdir(parents=True, exist_ok=True)

    if not audio_dir.exists():
        return []

    tracks = []
    for audio_file in sorted(audio_dir.iterdir()):
        if not audio_file.is_file() or audio_file.suffix.lower() not in SUPPORTED_AUDIO_EXTENSIONS:
            continue

        tracks.append(track_payload(audio_file))
    return tracks


def ensure_subtitles(track: dict) -> None:
    return


def is_track_generating(track_slug: str) -> bool:
    with _GENERATING_TRACKS_LOCK:
        return track_slug in _GENERATING_TRACKS


def get_track_generation_error(track_slug: str) -> str | None:
    with _GENERATING_TRACKS_LOCK:
        return _GENERATION_ERRORS.get(track_slug)


def estimate_remaining_seconds(timing: dict[str, float], now: float | None = None) -> float:
    current_time = monotonic() if now is None else now
    elapsed = current_time - timing['started_at']
    bias_reduction = min(0.25, elapsed / 80.0)
    adjusted_total = timing['estimated_total_seconds'] * (1.0 - bias_reduction)
    remaining = adjusted_total - elapsed
    return max(0.0, remaining)


def get_track_eta_seconds(track_slug: str) -> float | None:
    with _GENERATING_TRACKS_LOCK:
        if track_slug not in _GENERATION_TIMINGS:
            return None

        now = monotonic()
        ordered_timings = sorted(
            _GENERATION_TIMINGS.items(),
            key=lambda item: (item[1]['started_at'], item[0]),
        )
        cumulative_eta = 0.0
        for slug, timing in ordered_timings:
            cumulative_eta += estimate_remaining_seconds(timing, now=now)
            if slug == track_slug:
                return cumulative_eta

        return None


def start_track_generation(track: dict) -> bool:
    global _seconds_per_audio_second

    track_slug = track['slug']
    audio_duration_seconds = 0.0
    try:
        audio_duration_seconds = get_audio_duration_seconds(track['audio_file'])
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
        _GENERATION_ERRORS.pop(track_slug, None)
        _GENERATION_TIMINGS[track_slug] = {
            'started_at': started_at,
            'estimated_total_seconds': estimated_total_seconds,
            'audio_duration_seconds': audio_duration_seconds,
        }

    def run_generation() -> None:
        global _seconds_per_audio_second
        started = monotonic()
        try:
            segments = get_subtitles(track['audio_file'])
            save_segments_json(segments, Path(track['subtitle_file']))
            with _GENERATING_TRACKS_LOCK:
                _GENERATION_ERRORS.pop(track_slug, None)
        except Exception as exc:
            with _GENERATING_TRACKS_LOCK:
                _GENERATION_ERRORS[track_slug] = str(exc)
            logger.exception('Subtitle generation failed for %s', track_slug)
        finally:
            with _GENERATING_TRACKS_LOCK:
                timing = _GENERATION_TIMINGS.pop(track_slug, None)
                if timing:
                    audio_seconds = timing.get('audio_duration_seconds', 0.0)
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

    Thread(target=run_generation, daemon=True).start()
    return True


def get_track(track_slug: str | None, tracks: list[dict]) -> dict | None:
    if not tracks:
        return None

    if track_slug:
        for track in tracks:
            if track['slug'] == track_slug:
                return track
    return None


def load_track_segments(track: dict) -> list[dict]:
    return load_segments_json(Path(track['subtitle_file']))
