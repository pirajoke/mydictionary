"""Validated, versioned catalog of learning content packs."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path, PurePosixPath
import re
from typing import Any


# Leaves room for topic/action prefixes inside Telegram's 64-byte callback limit.
PACK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,39}$")
LANGUAGE_RE = re.compile(r"^[a-z]{2,3}$")
VISIBILITIES = {"public", "admin"}
STATUSES = {"draft", "published", "archived"}


class CatalogError(ValueError):
    """Raised when checked-in catalog data violates its contract."""


@dataclass(frozen=True)
class ContentPack:
    pack_id: str
    language: str
    label: str
    title: str
    description: str
    filename: str
    storage_key: str
    visibility: str
    is_free: bool
    status: str
    version: int
    word_count: int

    def visible_to(self, role: str) -> bool:
        return self.status == "published" and (
            self.visibility == "public" or role == "admin"
        )


class ContentCatalog:
    def __init__(self, packs: list[ContentPack], root: Path):
        self.packs = tuple(packs)
        self.root = root
        self._by_id = {pack.pack_id: pack for pack in packs}

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
                if pack.language == language
            ),
            None,
        )

    def words(self, pack: ContentPack) -> list[dict[str, Any]]:
        return json.loads((self.root / pack.filename).read_text(encoding="utf-8"))


def _required_text(raw: dict[str, Any], field: str, pack_id: str) -> str:
    value = str(raw.get(field, "")).strip()
    if not value:
        raise CatalogError(f"Pack {pack_id} requires {field}")
    return value


def _safe_filename(value: str, pack_id: str) -> str:
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or len(path.parts) != 1:
        raise CatalogError(f"Pack {pack_id} has an unsafe filename")
    if path.suffix != ".json":
        raise CatalogError(f"Pack {pack_id} content must be JSON")
    return value


def load_catalog(root: Path | None = None) -> ContentCatalog:
    project_root = (root or Path(__file__).resolve().parents[1]).resolve()
    catalog_path = project_root / "content" / "catalog.json"
    try:
        raw_catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CatalogError(f"Cannot load content catalog: {exc}") from exc
    if raw_catalog.get("schema_version") != 1:
        raise CatalogError("Unsupported content catalog schema")
    raw_packs = raw_catalog.get("packs")
    if not isinstance(raw_packs, list) or not raw_packs:
        raise CatalogError("Content catalog requires packs")

    packs: list[ContentPack] = []
    seen_ids: set[str] = set()
    seen_storage_keys: set[str] = set()
    for raw in raw_packs:
        if not isinstance(raw, dict):
            raise CatalogError("Every content pack must be an object")
        pack_id = str(raw.get("pack_id", "")).strip()
        if not PACK_ID_RE.fullmatch(pack_id) or pack_id in seen_ids:
            raise CatalogError(f"Invalid or duplicate pack_id: {pack_id}")
        seen_ids.add(pack_id)
        language = str(raw.get("language", "")).strip().lower()
        visibility = str(raw.get("visibility", "")).strip().lower()
        status = str(raw.get("status", "")).strip().lower()
        filename = _safe_filename(
            _required_text(raw, "filename", pack_id), pack_id
        )
        storage_key = _required_text(raw, "storage_key", pack_id)
        if (
            not re.fullmatch(r"^[a-z0-9_]{2,16}$", storage_key)
            or storage_key in seen_storage_keys
        ):
            raise CatalogError(f"Pack {pack_id} has invalid storage_key")
        seen_storage_keys.add(storage_key)
        if not LANGUAGE_RE.fullmatch(language):
            raise CatalogError(f"Pack {pack_id} has an invalid language")
        if visibility not in VISIBILITIES or status not in STATUSES:
            raise CatalogError(f"Pack {pack_id} has invalid publication metadata")
        if type(raw.get("is_free")) is not bool:
            raise CatalogError(f"Pack {pack_id} requires boolean is_free")
        version = raw.get("version")
        word_count = raw.get("word_count")
        if type(version) is not int or version < 1:
            raise CatalogError(f"Pack {pack_id} requires a positive version")
        if type(word_count) is not int or word_count < 1:
            raise CatalogError(f"Pack {pack_id} requires a positive word_count")
        content_path = project_root / filename
        try:
            words = json.loads(content_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CatalogError(f"Cannot load pack {pack_id}: {exc}") from exc
        if not isinstance(words, list) or len(words) != word_count:
            raise CatalogError(
                f"Pack {pack_id} declares {word_count} words, found "
                f"{len(words) if isinstance(words, list) else 'invalid content'}"
            )
        packs.append(
            ContentPack(
                pack_id=pack_id,
                language=language,
                label=_required_text(raw, "label", pack_id),
                title=_required_text(raw, "title", pack_id),
                description=_required_text(raw, "description", pack_id),
                filename=filename,
                storage_key=storage_key,
                visibility=visibility,
                is_free=raw["is_free"],
                status=status,
                version=version,
                word_count=word_count,
            )
        )
    return ContentCatalog(packs, project_root)
