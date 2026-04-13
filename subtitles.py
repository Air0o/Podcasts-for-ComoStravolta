import argparse
import json
from functools import lru_cache
from pathlib import Path

import whisper
from whisper.audio import SAMPLE_RATE


@lru_cache(maxsize=4)
def load_model(model_name: str = "large"):
    return whisper.load_model(model_name)


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