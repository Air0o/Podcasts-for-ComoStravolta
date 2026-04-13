import argparse
import json
from functools import lru_cache
from pathlib import Path
from threading import Lock, Thread

import whisper
from whisper.audio import SAMPLE_RATE


_PRELOADING_MODELS: set[str] = set()
_PRELOADING_MODELS_LOCK = Lock()
_TRANSCRIBE_LOCKS: dict[str, Lock] = {}
_TRANSCRIBE_LOCKS_GUARD = Lock()


@lru_cache(maxsize=4)
def load_model(model_name: str = "large"):
    return whisper.load_model(model_name)


def preload_model_in_background(model_name: str = "large") -> bool:
    with _PRELOADING_MODELS_LOCK:
        if model_name in _PRELOADING_MODELS:
            return False
        _PRELOADING_MODELS.add(model_name)

    def _run() -> None:
        try:
            load_model(model_name)
        finally:
            with _PRELOADING_MODELS_LOCK:
                _PRELOADING_MODELS.discard(model_name)

    Thread(target=_run, name=f"whisper-preload-{model_name}", daemon=True).start()
    return True


def _get_transcribe_lock(model_name: str) -> Lock:
    with _TRANSCRIBE_LOCKS_GUARD:
        lock = _TRANSCRIBE_LOCKS.get(model_name)
        if lock is None:
            lock = Lock()
            _TRANSCRIBE_LOCKS[model_name] = lock
        return lock


def normalize_segments(segments: list[dict]) -> list[dict]:
    normalized = []
    for segment in segments:
        text = str(segment.get("text", "")).strip()
        if not text:
            continue
        normalized.append(
            {
                "start": float(segment.get("start", 0.0)),
                "end": float(segment.get("end", 0.0)),
                "text": text,
            }
        )
    return normalized


def get_subtitles(file_path: str, model_name: str = "large") -> list[dict]:
    model = load_model(model_name)
    # Whisper model inference is not reliable under concurrent access.
    with _get_transcribe_lock(model_name):
        result = model.transcribe(file_path)
    return normalize_segments(result.get("segments", []))


def get_audio_duration_seconds(file_path: str) -> float:
    audio = whisper.load_audio(file_path)
    return float(len(audio)) / float(SAMPLE_RATE)


def save_segments_json(segments: list[dict], output_file: Path) -> None:
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open("w", encoding="utf-8") as f:
        json.dump(segments, f, ensure_ascii=True, indent=2)


def load_segments_json(input_file: Path) -> list[dict]:
    with input_file.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return normalize_segments(data)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("file_path")
    parser.add_argument("--output", help="Path to write JSON segments")
    parser.add_argument("--model", default="small")
    args = parser.parse_args()

    segments = get_subtitles(args.file_path, args.model)
    if args.output:
        save_segments_json(segments, Path(args.output))
        print(f"Saved {len(segments)} segments to {args.output}")
    else:
        print(json.dumps(segments, ensure_ascii=True, indent=2))