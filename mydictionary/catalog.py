"""Validated, versioned catalog of language-learning content packs."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping
import unicodedata

from .content import (
    ENTRY_ID_RE,
    PROGRESS_FIELDS,
    PROGRESS_ID_RE,
    content_progress_id,
    legacy_progress_id,
)


PACK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")
LANGUAGE_RE = re.compile(r"^[a-z]{2,3}$")
STORAGE_KEY_RE = re.compile(r"^[a-z0-9_]{2,16}$")
TOPIC_ID_RE = re.compile(r"^[a-z][a-z0-9-]{1,23}$")
TRANSCRIPTION_SYSTEM_RE = re.compile(r"^[a-z][a-z0-9-]{1,31}$")
LOCALE_RE = re.compile(r"^[a-z]{2,3}-[A-Z]{2}$")
RATE_RE = re.compile(r"^[+-][0-9]{1,2}%$")
VISIBILITIES = {"public", "admin"}
STATUSES = {"draft", "published", "archived"}
DIRECTIONS = {"ltr", "rtl"}
TRANSCRIPTION_POSITIONS = {"before", "after", "hidden"}
PACK_FIELDS = {
    "pack_id",
    "target_language",
    "meaning_language",
    "direction",
    "flag",
    "meaning_flag",
    "label",
    "title",
    "description",
    "filename",
    "storage_key",
    "visibility",
    "is_free",
    "status",
    "content_schema",
    "content_version",
    "entry_count",
    "pronunciation",
}


class CatalogError(ValueError):
    """Raised when checked-in catalog data violates its contract."""


@dataclass(frozen=True)
class PronunciationConfig:
    transcription_system: str
    transcription_position: str
    tts_locale: str
    tts_voice: str
    tts_rate: str


@dataclass(frozen=True)
class ContentPack:
    pack_id: str
    target_language: str
    meaning_language: str
    direction: str
    flag: str
    meaning_flag: str
    label: str
    title: str
    description: str
    filename: str
    storage_key: str
    visibility: str
    is_free: bool
    status: str
    content_schema: int
    content_version: int
    entry_count: int
    pronunciation: PronunciationConfig

    @property
    def language(self) -> str:
        """Compatibility alias for persisted profiles created before schema v2."""
        return self.target_language

    @property
    def word_count(self) -> int:
        return self.entry_count

    @property
    def version(self) -> int:
        return self.content_version

    def visible_to(self, role: str) -> bool:
        return self.status == "published" and (
            self.visibility == "public" or role == "admin"
        )


class ContentCatalog:
    def __init__(
        self,
        packs: list[ContentPack],
        entries: Mapping[str, tuple[dict[str, Any], ...]],
        topic_labels: Mapping[str, str],
        root: Path,
    ):
        self.packs = tuple(packs)
        self.topic_labels = dict(topic_labels)
        self.root = root
        self._by_id = {pack.pack_id: pack for pack in packs}
        self._entries = dict(entries)

    def get(self, pack_id: str) -> ContentPack | None:
        return self._by_id.get(pack_id)

    def require(self, pack_id: str) -> ContentPack:
        pack = self.get(pack_id)
        if pack is None:
            raise CatalogError(f"Unknown content pack: {pack_id}")
        return pack

    def visible_packs(self, role: str) -> tuple[ContentPack, ...]:
        return tuple(pack for pack in self.packs if pack.visible_to(role))

    def pack_for_language(self, language: str, role: str) -> ContentPack | None:
        return next(
            (
                pack
                for pack in self.visible_packs(role)
                if pack.target_language == language
            ),
            None,
        )

    def words(self, pack: ContentPack) -> list[dict[str, Any]]:
        return [dict(entry) for entry in self._entries[pack.pack_id]]


def _has_unsafe_text(value: str) -> bool:
    return any(unicodedata.category(character) in {"Cc", "Cf"} for character in value)


def _required_text(
    raw: Mapping[str, Any],
    field: str,
    owner: str,
    *,
    maximum: int = 512,
) -> str:
    value = raw.get(field)
    if not isinstance(value, str):
        raise CatalogError(f"{owner} requires text field {field}")
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > maximum
        or normalized != unicodedata.normalize("NFC", normalized)
        or _has_unsafe_text(normalized)
    ):
        raise CatalogError(f"{owner} has invalid text field {field}")
    return normalized


def _optional_text(
    raw: Mapping[str, Any], field: str, owner: str, *, maximum: int = 512
) -> str:
    value = raw.get(field, "")
    if not isinstance(value, str):
        raise CatalogError(f"{owner} requires text field {field}")
    normalized = value.strip()
    if (
        len(normalized) > maximum
        or normalized != unicodedata.normalize("NFC", normalized)
        or _has_unsafe_text(normalized)
    ):
        raise CatalogError(f"{owner} has invalid text field {field}")
    return normalized


def _safe_filename(value: str, pack_id: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
        raise CatalogError(f"Pack {pack_id} has an unsafe filename")
    if path.suffix != ".json":
        raise CatalogError(f"Pack {pack_id} content must be JSON")
    return value


def _read_json(path: Path, owner: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CatalogError(f"Cannot load {owner}") from exc


def _parse_topics(raw_catalog: Mapping[str, Any]) -> dict[str, str]:
    raw_topics = raw_catalog.get("topics")
    if not isinstance(raw_topics, list) or not raw_topics:
        raise CatalogError("Content catalog requires topics")
    result: dict[str, str] = {}
    for raw in raw_topics:
        if not isinstance(raw, dict) or set(raw) != {"topic_id", "label"}:
            raise CatalogError("Every topic requires topic_id and label")
        topic_id = str(raw.get("topic_id") or "").strip()
        if not TOPIC_ID_RE.fullmatch(topic_id) or topic_id in result:
            raise CatalogError(f"Invalid or duplicate topic_id: {topic_id}")
        result[topic_id] = _required_text(raw, "label", f"Topic {topic_id}", maximum=80)
    return result


def _parse_pronunciation(raw: Any, pack_id: str) -> PronunciationConfig:
    required = {
        "transcription_system",
        "transcription_position",
        "tts_locale",
        "tts_voice",
        "tts_rate",
    }
    if not isinstance(raw, dict) or set(raw) != required:
        raise CatalogError(f"Pack {pack_id} has invalid pronunciation metadata")
    system = str(raw.get("transcription_system") or "").strip().lower()
    position = str(raw.get("transcription_position") or "").strip().lower()
    locale = str(raw.get("tts_locale") or "").strip()
    voice = _required_text(raw, "tts_voice", f"Pack {pack_id}", maximum=128)
    rate = str(raw.get("tts_rate") or "").strip()
    if not TRANSCRIPTION_SYSTEM_RE.fullmatch(system):
        raise CatalogError(f"Pack {pack_id} has invalid transcription system")
    if position not in TRANSCRIPTION_POSITIONS:
        raise CatalogError(f"Pack {pack_id} has invalid transcription position")
    if system == "none" and position != "hidden":
        raise CatalogError(f"Pack {pack_id} must hide missing transcription")
    if system != "none" and position == "hidden":
        raise CatalogError(f"Pack {pack_id} cannot hide declared transcription")
    if not LOCALE_RE.fullmatch(locale) or not RATE_RE.fullmatch(rate):
        raise CatalogError(f"Pack {pack_id} has invalid TTS configuration")
    return PronunciationConfig(system, position, locale, voice, rate)


def _legacy_entry(raw: Any, pack_id: str, index: int) -> dict[str, Any]:
    owner = f"Pack {pack_id} entry {index}"
    if not isinstance(raw, dict):
        raise CatalogError(f"{owner} must be an object")
    target = _required_text(raw, "en", owner)
    meaning = _required_text(raw, "ru", owner)
    progress_id = legacy_progress_id(target, meaning)
    return {
        "entry_id": progress_id,
        "progress_id": progress_id,
        "target": target,
        "meaning": meaning,
        "accepted_meanings": (meaning,),
        "transcription": _optional_text(raw, "ipa", owner, maximum=160),
        "speech": _optional_text(raw, "reading", owner, maximum=512) or target,
        "topics": (),
        "example_target": _optional_text(raw, "example", owner, maximum=1000),
        "example_meaning": "",
    }


def _v2_entry(
    raw: Any,
    pack: ContentPack,
    index: int,
    topic_labels: Mapping[str, str],
) -> dict[str, Any]:
    owner = f"Pack {pack.pack_id} entry {index}"
    required = {
        "entry_id",
        "target",
        "meaning",
        "transcription",
        "speech",
        "topics",
        "example",
    }
    optional = {"legacy_progress_id", "accepted_meanings"}
    if (
        not isinstance(raw, dict)
        or not required.issubset(raw)
        or set(raw).difference(required | optional)
    ):
        raise CatalogError(f"{owner} has invalid fields")
    if PROGRESS_FIELDS.intersection(raw):
        raise CatalogError(f"{owner} contains learner progress")
    entry_id = str(raw.get("entry_id") or "").strip()
    if not ENTRY_ID_RE.fullmatch(entry_id):
        raise CatalogError(f"{owner} has invalid entry_id")
    target = _required_text(raw, "target", owner)
    meaning = _required_text(raw, "meaning", owner)
    raw_meanings = raw.get("accepted_meanings", [meaning])
    if not isinstance(raw_meanings, list) or not 1 <= len(raw_meanings) <= 12:
        raise CatalogError(f"{owner} has invalid accepted_meanings")
    accepted_meanings = tuple(
        _required_text(
            {"value": value},
            "value",
            f"{owner} accepted meaning {position}",
        )
        for position, value in enumerate(raw_meanings, 1)
    )
    normalized_meanings = [value.casefold() for value in accepted_meanings]
    if (
        meaning.casefold() not in normalized_meanings
        or len(normalized_meanings) != len(set(normalized_meanings))
    ):
        raise CatalogError(f"{owner} has invalid accepted_meanings")
    transcription = _optional_text(raw, "transcription", owner, maximum=160)
    if pack.pronunciation.transcription_system != "none" and not transcription:
        raise CatalogError(f"{owner} requires transcription")
    if pack.pronunciation.transcription_system == "none" and transcription:
        raise CatalogError(f"{owner} has unexpected transcription")
    speech = _required_text(raw, "speech", owner)
    topics = raw.get("topics")
    if (
        not isinstance(topics, list)
        or not topics
        or any(not isinstance(topic, str) or topic not in topic_labels for topic in topics)
        or len(topics) != len(set(topics))
    ):
        raise CatalogError(f"{owner} has invalid topics")
    example = raw.get("example")
    if example is not None and (
        not isinstance(example, dict) or set(example) != {"target", "meaning"}
    ):
        raise CatalogError(f"{owner} has invalid example")
    progress_id = str(raw.get("legacy_progress_id") or "").strip()
    if progress_id and not PROGRESS_ID_RE.fullmatch(progress_id):
        raise CatalogError(f"{owner} has invalid legacy_progress_id")
    return {
        "entry_id": entry_id,
        "progress_id": progress_id or content_progress_id(pack.pack_id, entry_id),
        "target": target,
        "meaning": meaning,
        "accepted_meanings": accepted_meanings,
        "transcription": transcription,
        "speech": speech,
        "topics": tuple(topics),
        "example_target": (
            _required_text(example, "target", f"{owner} example", maximum=1000)
            if example is not None
            else ""
        ),
        "example_meaning": (
            _required_text(example, "meaning", f"{owner} example", maximum=1000)
            if example is not None
            else ""
        ),
    }


def _load_entries(
    root: Path,
    pack: ContentPack,
    topic_labels: Mapping[str, str],
) -> tuple[dict[str, Any], ...]:
    raw_content = _read_json(root / pack.filename, f"pack {pack.pack_id}")
    if pack.content_schema == 1:
        if not isinstance(raw_content, list):
            raise CatalogError(f"Pack {pack.pack_id} requires legacy entry list")
        entries = [
            _legacy_entry(raw, pack.pack_id, index)
            for index, raw in enumerate(raw_content, 1)
        ]
    elif pack.content_schema == 2:
        if (
            not isinstance(raw_content, dict)
            or set(raw_content) != {"schema_version", "entries"}
            or raw_content.get("schema_version") != 2
            or not isinstance(raw_content.get("entries"), list)
        ):
            raise CatalogError(f"Pack {pack.pack_id} requires content schema 2")
        entries = [
            _v2_entry(raw, pack, index, topic_labels)
            for index, raw in enumerate(raw_content["entries"], 1)
        ]
    else:
        raise CatalogError(f"Pack {pack.pack_id} has unsupported content schema")
    if len(entries) != pack.entry_count:
        raise CatalogError(
            f"Pack {pack.pack_id} declares {pack.entry_count} entries, "
            f"found {len(entries)}"
        )
    for field in ("entry_id", "progress_id"):
        values = [entry[field] for entry in entries]
        if len(values) != len(set(values)):
            raise CatalogError(f"Pack {pack.pack_id} has duplicate {field}")
    return tuple(entries)


def load_catalog(root: Path | None = None) -> ContentCatalog:
    project_root = (root or Path(__file__).resolve().parents[1]).resolve()
    raw_catalog = _read_json(project_root / "content" / "catalog.json", "catalog")
    if not isinstance(raw_catalog, dict) or raw_catalog.get("schema_version") != 2:
        raise CatalogError("Unsupported content catalog schema")
    if set(raw_catalog) != {"schema_version", "topics", "packs"}:
        raise CatalogError("Content catalog has invalid top-level fields")
    topic_labels = _parse_topics(raw_catalog)
    raw_packs = raw_catalog.get("packs")
    if not isinstance(raw_packs, list) or not raw_packs:
        raise CatalogError("Content catalog requires packs")

    packs: list[ContentPack] = []
    seen_ids: set[str] = set()
    seen_storage_keys: set[str] = set()
    for raw in raw_packs:
        if not isinstance(raw, dict) or set(raw) != PACK_FIELDS:
            raise CatalogError("Every content pack must match the pack contract")
        pack_id = str(raw.get("pack_id") or "").strip()
        if not PACK_ID_RE.fullmatch(pack_id) or pack_id in seen_ids:
            raise CatalogError(f"Invalid or duplicate pack_id: {pack_id}")
        seen_ids.add(pack_id)
        target_language = str(raw.get("target_language") or "").strip().lower()
        meaning_language = str(raw.get("meaning_language") or "").strip().lower()
        if not LANGUAGE_RE.fullmatch(target_language) or not LANGUAGE_RE.fullmatch(
            meaning_language
        ):
            raise CatalogError(f"Pack {pack_id} has invalid language metadata")
        storage_key = str(raw.get("storage_key") or "").strip()
        if not STORAGE_KEY_RE.fullmatch(storage_key) or storage_key in seen_storage_keys:
            raise CatalogError(f"Pack {pack_id} has invalid storage_key")
        seen_storage_keys.add(storage_key)
        visibility = str(raw.get("visibility") or "").strip().lower()
        status = str(raw.get("status") or "").strip().lower()
        direction = str(raw.get("direction") or "").strip().lower()
        if visibility not in VISIBILITIES or status not in STATUSES:
            raise CatalogError(f"Pack {pack_id} has invalid publication metadata")
        if direction not in DIRECTIONS:
            raise CatalogError(f"Pack {pack_id} has invalid writing direction")
        if type(raw.get("is_free")) is not bool:
            raise CatalogError(f"Pack {pack_id} requires boolean is_free")
        content_schema = raw.get("content_schema")
        content_version = raw.get("content_version")
        entry_count = raw.get("entry_count")
        if content_schema not in {1, 2}:
            raise CatalogError(f"Pack {pack_id} has unsupported content schema")
        if type(content_version) is not int or content_version < 1:
            raise CatalogError(f"Pack {pack_id} requires a positive content_version")
        if type(entry_count) is not int or entry_count < 1:
            raise CatalogError(f"Pack {pack_id} requires a positive entry_count")
        pack = ContentPack(
            pack_id=pack_id,
            target_language=target_language,
            meaning_language=meaning_language,
            direction=direction,
            flag=_required_text(raw, "flag", f"Pack {pack_id}", maximum=16),
            meaning_flag=_required_text(
                raw, "meaning_flag", f"Pack {pack_id}", maximum=16
            ),
            label=_required_text(raw, "label", f"Pack {pack_id}", maximum=80),
            title=_required_text(raw, "title", f"Pack {pack_id}", maximum=160),
            description=_required_text(
                raw, "description", f"Pack {pack_id}", maximum=500
            ),
            filename=_safe_filename(
                _required_text(raw, "filename", f"Pack {pack_id}", maximum=120),
                pack_id,
            ),
            storage_key=storage_key,
            visibility=visibility,
            is_free=raw["is_free"],
            status=status,
            content_schema=content_schema,
            content_version=content_version,
            entry_count=entry_count,
            pronunciation=_parse_pronunciation(raw.get("pronunciation"), pack_id),
        )
        for topic_id in topic_labels:
            if len(f"ltopic:{pack_id}:{topic_id}".encode("utf-8")) > 64:
                raise CatalogError(f"Pack {pack_id} creates oversized topic callback")
        packs.append(pack)

    entries = {
        pack.pack_id: _load_entries(project_root, pack, topic_labels) for pack in packs
    }
    return ContentCatalog(packs, entries, topic_labels, project_root)
