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


def _parse_cell(value: str | None, *, row: int, language: str) -> tuple[str, str, str]:
    parts = [part.strip() for part in (value or "").split("|")]
    if len(parts) not in {2, 3} or not all(parts):
        raise SourceError(
            f"row {row}: {language} must be target|transcription[|speech]"
        )
    target, transcription = parts[:2]
    speech = parts[2] if len(parts) == 3 else target
    return (
        _required(target, row=row, column=f"{language}.target"),
        _required(transcription, row=row, column=f"{language}.transcription"),
        _required(speech, row=row, column=f"{language}.speech"),
    )


def load_rows(path: Path = SOURCE) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as source:
        reader = csv.DictReader(source, delimiter="\t")
        if tuple(reader.fieldnames or ()) != HEADER:
            raise SourceError(f"unexpected header in {path.relative_to(ROOT)}")
        rows = list(reader)

    if len(rows) != 100:
        raise SourceError(f"expected 100 source rows, found {len(rows)}")

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
            target, _, _ = _parse_cell(
                row[pack.language], row=number, language=pack.language
            )
            target_key = target.casefold()
            if target_key in targets[pack.language]:
                raise SourceError(
                    f"row {number}: duplicate {pack.language} target {target}"
                )
            targets[pack.language].add(target_key)

    if topic_counts != Counter({topic: 10 for topic in TOPICS}):
        raise SourceError(f"expected ten entries per topic, found {dict(topic_counts)}")
    return rows


def build_documents(path: Path = SOURCE) -> dict[str, dict[str, object]]:
    rows = load_rows(path)
    documents: dict[str, dict[str, object]] = {}
    for pack in PACKS:
        entries = []
        for number, row in enumerate(rows, 2):
            target, transcription, speech = _parse_cell(
                row[pack.language], row=number, language=pack.language
            )
            meaning = _required(
                row[pack.meaning_column],
                row=number,
                column=pack.meaning_column,
            )
            entries.append(
                {
                    "entry_id": row["entry_id"].strip(),
                    "target": target,
                    "meaning": meaning,
                    "transcription": transcription,
                    "speech": speech,
                    "topics": [row["topic"].strip()],
                    "example": None,
                }
            )
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
