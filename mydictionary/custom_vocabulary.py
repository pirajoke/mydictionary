"""Bounded custom-vocabulary parsing and multimodal extraction contracts."""

from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import re
import unicodedata
from typing import Any, Iterable, Mapping


MAX_IMPORT_ENTRIES = 40
MAX_CUSTOM_WORDS_PER_LANGUAGE = 500
MAX_PASTE_CHARS = 8000
MAX_UPLOAD_BYTES = 8 * 1024 * 1024

CUSTOM_VOCABULARY_RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "entries": {
            "type": "array",
            "minItems": 1,
            "maxItems": MAX_IMPORT_ENTRIES,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "target": {"type": "string", "minLength": 1, "maxLength": 120},
                    "meaning": {"type": "string", "minLength": 1, "maxLength": 240},
                    "transcription": {"type": "string", "maxLength": 160},
                },
                "required": ["target", "meaning", "transcription"],
            },
        }
    },
    "required": ["entries"],
}

CUSTOM_VOCABULARY_INSTRUCTIONS = (
    "Extract only useful vocabulary terms that the learner supplied. Return each "
    "term in the requested target language, a concise translation in the requested "
    "meaning language, and a learner-friendly transcription when it is useful. "
    "Do not add unrelated vocabulary, definitions, commentary, examples, or duplicate "
    "terms. Preserve phrases as phrases. Return at most 40 entries."
)


@dataclass(frozen=True)
class CustomVocabularyCandidate:
    target: str
    meaning: str = ""
    transcription: str = ""
    source_kind: str = "text"

    @property
    def normalized_target(self) -> str:
        return normalize_target(self.target)


def _bounded_text(value: Any, maximum: int, *, required: bool = False) -> str:
    if not isinstance(value, str):
        raise ValueError("Vocabulary fields must be text")
    cleaned = " ".join(unicodedata.normalize("NFKC", value).split())
    if required and not cleaned:
        raise ValueError("Vocabulary target cannot be empty")
    if len(cleaned) > maximum:
        raise ValueError("Vocabulary field is too long")
    return cleaned


def normalize_target(value: str) -> str:
    return _bounded_text(value, 120, required=True).casefold()


def _split_pasted_line(line: str) -> tuple[str, str]:
    candidate = re.sub(
        r"^\s*(?:(?:\d{1,3}[.)])|[•*·])\s*",
        "",
        line,
        count=1,
    ).strip()
    for pattern in (r"\t+", r"\s+[—–-]\s+", r"\s*;\s*", r"\s*:\s*"):
        parts = re.split(pattern, candidate, maxsplit=1)
        if len(parts) == 2 and parts[0].strip() and parts[1].strip():
            return parts[0].strip(), parts[1].strip()
    return candidate, ""


def parse_pasted_vocabulary(text: str) -> tuple[CustomVocabularyCandidate, ...]:
    if not isinstance(text, str) or not text.strip():
        raise ValueError("Vocabulary paste is empty")
    if len(text) > MAX_PASTE_CHARS:
        raise ValueError("Vocabulary paste is too large")
    rows: list[CustomVocabularyCandidate] = []
    seen: set[str] = set()
    for raw_line in text.splitlines():
        if not raw_line.strip():
            continue
        target, meaning = _split_pasted_line(raw_line)
        target = _bounded_text(target, 120, required=True)
        meaning = _bounded_text(meaning, 240)
        normalized = normalize_target(target)
        if normalized in seen:
            continue
        seen.add(normalized)
        rows.append(CustomVocabularyCandidate(target, meaning, "", "text"))
        if len(rows) > MAX_IMPORT_ENTRIES:
            raise ValueError("Vocabulary import contains more than 40 entries")
    if not rows:
        raise ValueError("Vocabulary paste has no usable entries")
    return tuple(rows)


def validate_extracted_vocabulary(
    payload: Mapping[str, Any], *, source_kind: str
) -> tuple[CustomVocabularyCandidate, ...]:
    if source_kind not in {"text", "photo", "pdf", "voice"}:
        raise ValueError("Unsupported vocabulary source")
    if not isinstance(payload, Mapping) or set(payload) != {"entries"}:
        raise ValueError("Vocabulary extraction response is invalid")
    raw_entries = payload["entries"]
    if not isinstance(raw_entries, list) or not 1 <= len(raw_entries) <= MAX_IMPORT_ENTRIES:
        raise ValueError("Vocabulary extraction entry count is invalid")
    result: list[CustomVocabularyCandidate] = []
    seen: set[str] = set()
    expected_fields = {"target", "meaning", "transcription"}
    for raw in raw_entries:
        if not isinstance(raw, Mapping) or set(raw) != expected_fields:
            raise ValueError("Vocabulary extraction fields are invalid")
        target = _bounded_text(raw["target"], 120, required=True)
        meaning = _bounded_text(raw["meaning"], 240, required=True)
        transcription = _bounded_text(raw["transcription"], 160)
        normalized = normalize_target(target)
        if normalized in seen:
            continue
        seen.add(normalized)
        result.append(
            CustomVocabularyCandidate(target, meaning, transcription, source_kind)
        )
    if not result:
        raise ValueError("Vocabulary extraction has no unique entries")
    return tuple(result)


def text_enrichment_payload(
    entries: Iterable[CustomVocabularyCandidate],
    *,
    target_language: str,
    meaning_language: str,
) -> list[dict[str, str]]:
    items = [
        {
            "target": entry.target,
            "meaning": entry.meaning,
            "transcription": entry.transcription,
        }
        for entry in entries
    ]
    if not 1 <= len(items) <= MAX_IMPORT_ENTRIES:
        raise ValueError("Vocabulary input count is invalid")
    instruction = {
        "target_language": _bounded_text(target_language, 16, required=True),
        "meaning_language": _bounded_text(meaning_language, 16, required=True),
        "supplied_entries": items,
    }
    return [{"type": "input_text", "text": json.dumps(instruction, ensure_ascii=False)}]


def spoken_vocabulary_payload(
    transcript: str,
    *,
    target_language: str,
    meaning_language: str,
) -> list[dict[str, str]]:
    """Preserve one bounded voice transcript for structured list extraction."""
    instruction = {
        "target_language": _bounded_text(target_language, 16, required=True),
        "meaning_language": _bounded_text(meaning_language, 16, required=True),
        "task": (
            "Extract the vocabulary list the learner dictated. Separate distinct "
            "spoken words or phrases and use any supplied spoken translations."
        ),
        "transcript": _bounded_text(transcript, MAX_PASTE_CHARS, required=True),
    }
    return [{"type": "input_text", "text": json.dumps(instruction, ensure_ascii=False)}]


def build_multimodal_input(
    *,
    source_kind: str,
    content: bytes,
    mime_type: str,
    filename: str,
    target_language: str,
    meaning_language: str,
) -> list[dict[str, str]]:
    if not isinstance(content, bytes) or not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Vocabulary upload is empty or too large")
    prompt = {
        "target_language": _bounded_text(target_language, 16, required=True),
        "meaning_language": _bounded_text(meaning_language, 16, required=True),
        "task": "Extract vocabulary deliberately present in this learner upload.",
    }
    encoded = base64.b64encode(content).decode("ascii")
    items: list[dict[str, str]] = [
        {"type": "input_text", "text": json.dumps(prompt, ensure_ascii=False)}
    ]
    if source_kind == "photo" and mime_type in {"image/jpeg", "image/png", "image/webp"}:
        items.append(
            {
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{encoded}",
                "detail": "high",
            }
        )
    elif source_kind == "pdf" and mime_type == "application/pdf":
        safe_filename = re.sub(r"[^A-Za-z0-9._-]", "_", filename or "words.pdf")[:80]
        if not safe_filename.lower().endswith(".pdf"):
            safe_filename += ".pdf"
        items.append(
            {
                "type": "input_file",
                "filename": safe_filename,
                "file_data": f"data:application/pdf;base64,{encoded}",
                "detail": "low",
            }
        )
    else:
        raise ValueError("Unsupported vocabulary upload")
    return items
