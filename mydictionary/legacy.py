"""One-time import of the original single-user JSON state."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from .storage import DatabaseStore


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return fallback


def import_legacy_user(
    store: DatabaseStore,
    user_id: int,
    data_dir: Path,
    base_dir: Path,
    language_files: Mapping[str, str],
    profile_defaults: Mapping[str, Any],
) -> bool:
    """Import progress.json and per-word counters from the old data directory."""
    progress_path = data_dir / "progress.json"
    legacy_state_found = progress_path.exists()
    progress = dict(profile_defaults)
    progress.update(_read_json(progress_path, {}))

    words_by_language: dict[str, list[dict[str, Any]]] = {}
    sources = []
    for language, filename in language_files.items():
        data_path = data_dir / filename
        base_path = base_dir / filename
        source = data_path if data_path.exists() else base_path
        if data_path.exists() and data_path.resolve() != base_path.resolve():
            legacy_state_found = True
        words_by_language[language] = _read_json(source, [])
        sources.append(f"{language}:{'data' if source == data_path else 'base'}")

    # Do not mark a clean install as imported before its legacy volume is mounted.
    if not legacy_state_found:
        return False

    return store.import_legacy_state(
        int(user_id),
        progress,
        words_by_language,
        import_key=f"legacy-json-v1:{int(user_id)}",
        details=",".join(sources),
    )
