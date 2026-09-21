#!/usr/bin/env python3
"""Build the checked-in schema v2 basic packs from one aligned TSV source."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
import sys
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "content" / "basic_100.tsv"
TOPICS = (
    "greetings",
    "people",
    "food",
    "home",
    "travel",
    "time",
    "work",
    "health",
    "actions",
    "descriptions",
)
EXPECTED_SOURCE_ROWS = 500
ENTRIES_PER_TOPIC = 50

# These polysemous concepts are intentionally pinned to one everyday learning
# sense across every generated language.  Keeping the checks beside the source
# builder prevents a future upstream refresh from silently mixing unrelated
# senses (for example, ``driver`` as an animal handler or ``capital`` as money).
EXPECTED_ALIGNED_SENSES = {
    "call": {"en": "call", "fr": "appel", "de": "Anruf", "ar": "اِتِّصَال", "zh": "呼叫", "ru": "звоно́к", "es": "llamada"},
    "capital": {"en": "capital", "fr": "capitale", "de": "Hauptstadt", "ar": "عَاصِمَة", "zh": "首都", "ru": "столи́ца", "es": "capital"},
    "card": {"en": "card", "fr": "carte", "de": "Karte", "ar": "بِطَاقَة", "zh": "卡片", "ru": "ка́рточка", "es": "tarjeta"},
    "driver": {"en": "driver", "fr": "conducteur", "de": "Fahrer", "ar": "سَائِق", "zh": "司机", "ru": "води́тель", "es": "conductor"},
    "let": {"en": "let", "fr": "permettre", "de": "erlauben", "ar": "سَمَحَ", "zh": "让", "ru": "позволя́ть", "es": "permitir"},
    "light": {"en": "light", "fr": "lumière", "de": "Licht", "ar": "ضَوْء", "zh": "光", "ru": "свет", "es": "luz"},
    "miss": {"en": "miss", "fr": "manquer", "de": "vermissen", "ar": "اِشْتَاقَ إِلَى", "zh": "想念", "ru": "скуча́ть по", "es": "extrañar"},
    "news": {"en": "news", "fr": "nouvelles", "de": "Neuigkeiten", "ar": "أَخْبَار", "zh": "消息", "ru": "но́вости", "es": "noticias"},
    "note": {"en": "note", "fr": "note", "de": "Notiz", "ar": "مُلَاحَظَة", "zh": "字条", "ru": "заме́тка", "es": "nota"},
    "point": {"en": "point", "fr": "point", "de": "Punkt", "ar": "نُقْطَة", "zh": "点", "ru": "то́чка", "es": "punto"},
    "present": {"en": "present", "fr": "cadeau", "de": "Geschenk", "ar": "هَدِيَّة", "zh": "礼物", "ru": "пода́рок", "es": "regalo"},
    "sentence": {"en": "sentence", "fr": "phrase", "de": "Satz", "ar": "جُمْلَة", "zh": "句子", "ru": "предложе́ние", "es": "oración"},
    "spell": {"en": "spell", "fr": "épeler", "de": "buchstabieren", "ar": "هَجَّى", "zh": "拼写", "ru": "произноси́ть по бу́квам", "es": "deletrear"},
    "spelling": {"en": "spelling", "fr": "orthographe", "de": "Rechtschreibung", "ar": "تَهْجِئَة", "zh": "拼写法", "ru": "правописа́ние", "es": "ortografía"},
    "subject": {"en": "subject", "fr": "matière", "de": "Schulfach", "ar": "مَادَّة دِرَاسِيَّة", "zh": "学科", "ru": "уче́бный предме́т", "es": "asignatura"},
    "watch": {"en": "watch", "fr": "montre", "de": "Uhr", "ar": "سَاعَة يَد", "zh": "手表", "ru": "нару́чные часы́", "es": "reloj"},
}


@dataclass(frozen=True)
class PackSource:
    language: str
    filename: str
    meaning_column: str = "meaning_ru"


PACKS = (
    PackSource("en", "words_en_basic.json"),
    PackSource("fr", "words_fr_basic.json"),
    PackSource("de", "words_de_basic.json"),
    PackSource("ar", "words_ar_basic.json"),
    PackSource("zh", "words_zh_basic.json"),
    PackSource("ru", "words_ru_basic.json", "ru_definition"),
    PackSource("es", "words_es_basic.json"),
)
HEADER = (
    "entry_id",
    "topic",
    "meaning_ru",
    "ru_definition",
    *(pack.language for pack in PACKS),
)
ENTRY_ID_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{1,63}$")


class SourceError(ValueError):
    """Raised when the aligned source matrix is incomplete or ambiguous."""


def _required(value: str | None, *, row: int, column: str) -> str:
    normalized = unicodedata.normalize("NFC", (value or "").strip())
    if not normalized:
        raise SourceError(f"row {row}: {column} is required")
    if any(unicodedata.category(character) in {"Cc", "Cf"} for character in normalized):
        raise SourceError(f"row {row}: {column} contains a control character")
    return normalized


def _parse_cell(
    value: str | None, *, row: int, language: str
) -> tuple[str, str, str, tuple[str, ...]]:
    parts = [part.strip() for part in (value or "").split("|")]
    if len(parts) not in {2, 3, 4} or not all(parts):
        raise SourceError(
            f"row {row}: {language} must be "
            "target|transcription[|speech[|meaning;accepted meaning]]"
        )
    target, transcription = parts[:2]
    speech = parts[2] if len(parts) == 3 else target
    accepted_meanings: tuple[str, ...] = ()
    if len(parts) == 4:
        speech = parts[2]
        accepted_meanings = tuple(
            _required(item, row=row, column=f"{language}.accepted_meanings")
            for item in parts[3].split(";")
        )
        normalized = [item.casefold() for item in accepted_meanings]
        if len(accepted_meanings) > 12 or len(normalized) != len(set(normalized)):
            raise SourceError(
                f"row {row}: {language} has invalid accepted meanings"
            )
    return (
        _required(target, row=row, column=f"{language}.target"),
        _required(transcription, row=row, column=f"{language}.transcription"),
        _required(speech, row=row, column=f"{language}.speech"),
        accepted_meanings,
    )


def load_rows(path: Path = SOURCE) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        if tuple(reader.fieldnames or ()) != HEADER:
            raise SourceError(f"unexpected header in {path.relative_to(ROOT)}")
        rows = list(reader)

    if len(rows) != EXPECTED_SOURCE_ROWS:
        raise SourceError(
            f"expected {EXPECTED_SOURCE_ROWS} source rows, found {len(rows)}"
        )

    entry_ids: set[str] = set()
    targets = {pack.language: set() for pack in PACKS}
    topic_counts: Counter[str] = Counter()
    for number, row in enumerate(rows, 2):
        if None in row:
            raise SourceError(f"row {number}: unexpected extra column")
        entry_id = _required(row["entry_id"], row=number, column="entry_id")
        if not ENTRY_ID_RE.fullmatch(entry_id) or entry_id in entry_ids:
            raise SourceError(f"row {number}: invalid or duplicate entry_id {entry_id}")
        entry_ids.add(entry_id)

        topic = _required(row["topic"], row=number, column="topic")
        if topic not in TOPICS:
            raise SourceError(f"row {number}: unsupported topic {topic}")
        topic_counts[topic] += 1

        _required(row["meaning_ru"], row=number, column="meaning_ru")
        _required(row["ru_definition"], row=number, column="ru_definition")
        for pack in PACKS:
            target, _, _, _ = _parse_cell(
                row[pack.language], row=number, language=pack.language
            )
            expected = EXPECTED_ALIGNED_SENSES.get(entry_id, {}).get(pack.language)
            if expected is not None and target != expected:
                raise SourceError(
                    f"row {number}: {entry_id}.{pack.language} must stay {expected!r}"
                )
            target_key = target.casefold()
            if target_key in targets[pack.language]:
                raise SourceError(
                    f"row {number}: duplicate {pack.language} target {target}"
                )
            targets[pack.language].add(target_key)

    if topic_counts != Counter({topic: ENTRIES_PER_TOPIC for topic in TOPICS}):
        raise SourceError(
            f"expected {ENTRIES_PER_TOPIC} entries per topic, "
            f"found {dict(topic_counts)}"
        )
    return rows


def build_documents(path: Path = SOURCE) -> dict[str, dict[str, object]]:
    rows = load_rows(path)
    documents: dict[str, dict[str, object]] = {}
    for pack in PACKS:
        entries = []
        for number, row in enumerate(rows, 2):
            target, transcription, speech, accepted_meanings = _parse_cell(
                row[pack.language], row=number, language=pack.language
            )
            default_meaning = _required(
                row[pack.meaning_column],
                row=number,
                column=pack.meaning_column,
            )
            meaning = accepted_meanings[0] if accepted_meanings else default_meaning
            entry = {
                "entry_id": row["entry_id"].strip(),
                "target": target,
                "meaning": meaning,
                "transcription": transcription,
                "speech": speech,
                "topics": [row["topic"].strip()],
                "example": None,
            }
            if accepted_meanings:
                entry["accepted_meanings"] = list(accepted_meanings)
            entries.append(entry)
        documents[pack.filename] = {"schema_version": 2, "entries": entries}
    return documents


def render(document: dict[str, object]) -> str:
    return json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when checked-in pack files differ from the source matrix",
    )
    args = parser.parse_args(argv)

    try:
        documents = build_documents()
    except (OSError, UnicodeError, SourceError) as exc:
        print(f"basic pack source error: {exc}", file=sys.stderr)
        return 1

    stale: list[str] = []
    for filename, document in documents.items():
        output = ROOT / filename
        expected = render(document)
        if args.check:
            try:
                current = output.read_text(encoding="utf-8")
            except OSError:
                current = ""
            if current != expected:
                stale.append(filename)
        else:
            output.write_text(expected, encoding="utf-8")

    if stale:
        print(
            "generated basic packs are stale: " + ", ".join(stale),
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
