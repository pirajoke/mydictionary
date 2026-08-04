"""Canonical vocabulary accessors shared by content, storage, and learning flows."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping


PROGRESS_ID_RE = re.compile(r"^[0-9a-f]{64}$")
ENTRY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,63}$")
PROGRESS_FIELDS = frozenset(
    {
        "correct_count",
        "wrong_count",
        "last_seen",
        "interval",
        "next_review",
    }
)


def legacy_progress_id(term: str, meaning: str) -> str:
    """Return the historical identity used by existing database rows."""
    identity = json.dumps(
        [term.strip(), meaning.strip()],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def content_progress_id(pack_id: str, entry_id: str) -> str:
    """Return a stable v2 identity independent of wording and list position."""
    identity = json.dumps(
        ["content-v2", pack_id, entry_id],
        ensure_ascii=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


def target_text(word: Mapping[str, Any]) -> str:
    return str(word.get("target") or word.get("en") or "").strip()


def meaning_text(word: Mapping[str, Any]) -> str:
    return str(word.get("meaning") or word.get("ru") or "").strip()


def transcription_text(word: Mapping[str, Any]) -> str:
    return str(word.get("transcription") or word.get("ipa") or "").strip()


def speech_text(word: Mapping[str, Any]) -> str:
    return str(
        word.get("speech") or word.get("reading") or target_text(word)
    ).strip()


def example_target_text(word: Mapping[str, Any]) -> str:
    return str(word.get("example_target") or word.get("example") or "").strip()


def example_meaning_text(word: Mapping[str, Any]) -> str:
    return str(word.get("example_meaning") or "").strip()


def entry_topics(word: Mapping[str, Any]) -> tuple[str, ...]:
    value = word.get("topics") or ()
    if not isinstance(value, (list, tuple)):
        return ()
    return tuple(str(topic).strip() for topic in value if str(topic).strip())


def vocabulary_progress_id(word: Mapping[str, Any]) -> str:
    explicit = str(word.get("progress_id") or "").strip()
    if explicit:
        if not PROGRESS_ID_RE.fullmatch(explicit):
            raise ValueError("Vocabulary progress_id must be a SHA-256 hex digest")
        return explicit
    term = target_text(word)
    meaning = meaning_text(word)
    if not term or not meaning:
        raise ValueError("Vocabulary entries require target and meaning text")
    return legacy_progress_id(term, meaning)
