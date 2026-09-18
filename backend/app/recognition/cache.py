"""Recognition cache.

Keyed by (image bytes, prompt version, model, subject), so the same photo read
by the same prompt and model is never paid for twice. This is what makes it
possible to iterate on the verifier twenty times in an afternoon without
spending anything, and what makes `app.eval --no-llm` work.

It is a cache, never a source of truth: `backend/.cache/` is gitignored and
deleting it only costs money, not data (ADR 0001).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.config import CACHE_DIR
from app.schemas import RecognitionResult


def cache_key(image_sha256: str, prompt_version: str, model: str, subject: str) -> str:
    raw = f"{image_sha256}|{prompt_version}|{model}|{subject}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _path_for(key: str, cache_dir: Path | None) -> Path:
    # Resolved at call time, not bound as a default argument, so the location
    # stays overridable (tests, and a future per-environment cache dir).
    base = cache_dir if cache_dir is not None else CACHE_DIR
    return base / "recognition" / f"{key}.json"


def load(key: str, cache_dir: Path | None = None) -> RecognitionResult | None:
    path = _path_for(key, cache_dir)
    if not path.is_file():
        return None
    try:
        return RecognitionResult.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        # A stale or half-written entry is not worth a crash; re-recognising
        # costs money but always works.
        return None


def store(key: str, result: RecognitionResult, cache_dir: Path | None = None) -> None:
    path = _path_for(key, cache_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = result.model_dump(mode="json")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
