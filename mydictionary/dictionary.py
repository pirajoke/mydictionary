"""Public, portable dictionary projection of redistribution-approved content.

Never build this payload from learner storage or an authenticated role. The
explicit pack and field allowlists keep future catalog additions private until
their redistribution boundary has been reviewed.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from typing import Any, Mapping

from mydictionary.catalog import ContentCatalog
from mydictionary.content import accepted_meanings


REDISTRIBUTABLE_PACK_IDS = frozenset({
    "en-basics-100",
    "fr-basics-100",
    "de-basics-100",
    "ar-basics-100",
    "zh-basics-100",
    "ru-basics-100",
    "es-basics-100",
})


def build_dictionary_data(catalog: ContentCatalog) -> dict[str, Any]:
    """Return only public, free, published v2 starter content, without state."""
    packs = []
    for pack in catalog.packs:
        if not (
            pack.pack_id in REDISTRIBUTABLE_PACK_IDS
            and pack.visibility == "public"
            and pack.is_free
            and pack.status == "published"
            and pack.content_schema == 2
        ):
            continue
        entries = []
        for entry in catalog.words(pack):
            example = None
            if entry.get("example_target") and entry.get("example_meaning"):
                example = {
                    "target": entry["example_target"],
                    "meaning": entry["example_meaning"],
                }
            entries.append({
                "entry_id": entry["entry_id"],
                "target": entry["target"],
                "meaning": entry["meaning"],
                "accepted_meanings": list(accepted_meanings(entry)),
                "transcription": entry["transcription"],
                "example": example,
            })
        packs.append({
            "id": pack.pack_id,
            "label": pack.label,
            "title": pack.title,
            "target_language": pack.target_language,
            "meaning_language": pack.meaning_language,
            "direction": pack.direction,
            "content_version": pack.content_version,
            "entry_count": len(entries),
            "entries": entries,
        })
    return {"version": 1, "packs": packs}


def dictionary_download_defaults(
    query: Mapping[str, str], data: Mapping[str, Any]
) -> dict[str, str]:
    """Persist only supported language codes in a portable file, never raw args."""
    languages = {pack["target_language"] for pack in data["packs"]}
    target = query.get("target", "en")
    native = query.get("native", "ru")
    ui = query.get("ui", "en")
    target = target if target in languages else "en"
    native = native if native in languages else "ru"
    if native == target:
        native = "en" if target == "ru" else "ru"
    return {
        "target": target,
        "native": native,
        "ui": ui if ui in {"en", "ru", "fr"} else "en",
    }


def dictionary_revision(
    data: Mapping[str, Any], sources: Mapping[str, bytes]
) -> str:
    """Version only public content and its complete offline shell, never users."""
    public_contract = {
        "data": data,
        "manifest": dictionary_manifest(),
        "csp": dictionary_content_security_policy(),
    }
    serialized = json.dumps(
        public_contract, sort_keys=True, ensure_ascii=True, separators=(",", ":")
    ).encode("utf-8")
    digest = hashlib.sha256(serialized)
    for name, source in sorted(sources.items()):
        # Length framing prevents different boundaries producing the same input.
        encoded_name = name.encode("utf-8")
        digest.update(len(encoded_name).to_bytes(8, "big"))
        digest.update(encoded_name)
        digest.update(len(source).to_bytes(8, "big"))
        digest.update(source)
    return digest.hexdigest()[:16]


def escape_inline_asset(source: str, element: str) -> str:
    """Prevent a trusted JS/CSS asset containing a closing tag ending its block."""
    if element not in {"script", "style"}:
        raise ValueError("Unsupported inline asset element")
    return re.sub(rf"</{element}", lambda match: "<\\/" + match[0][2:], source,
                  flags=re.IGNORECASE)


def dictionary_content_security_policy(*, css: str = "", javascript: str = "") -> str:
    """Authorize exact inline download assets without allowing arbitrary code."""
    def hash_source(source: str) -> str:
        digest = base64.b64encode(hashlib.sha256(source.encode("utf-8")).digest()).decode("ascii")
        return f" 'sha256-{digest}'" if source else ""

    return (
        "default-src 'none'; img-src 'self' data:; "
        f"style-src 'self'{hash_source(css)}; "
        f"script-src 'self'{hash_source(javascript)}; "
        "connect-src 'self'; worker-src 'self'; manifest-src 'self'; "
        "form-action 'none'; frame-ancestors 'none'; base-uri 'none'"
    )


def dictionary_manifest() -> dict[str, Any]:
    return {
        "id": "/dictionary/",
        "name": "Lexi Dictionary",
        "short_name": "Lexi",
        "description": "A portable starter dictionary for seven languages.",
        "start_url": "/dictionary/",
        "scope": "/dictionary/",
        "display": "standalone",
        "background_color": "#f7f9fc",
        "theme_color": "#12202d",
        "icons": [{
            "src": "/static/mascot/lexi-telegram-avatar-v1.jpg",
            "sizes": "800x800",
            "type": "image/jpeg",
            "purpose": "any",
        }],
    }
