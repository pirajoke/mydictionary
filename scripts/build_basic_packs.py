#!/usr/bin/env python3
"""Build the checked-in schema v2 basic packs from one aligned TSV source."""

from __future__ import annotations

import argparse
import csv
from copy import deepcopy
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import re
import sys
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "content" / "basic_100.tsv"
EDITORIAL = ROOT / "content" / "german_editorial.json"
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
            target, _, _, _ = _parse_cell(
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


def load_editorial(path: Path, entries: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    """Validate the additive German overlay without allowing identity changes."""
    try:
        overlay = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise SourceError("invalid German editorial JSON") from exc
    if (not isinstance(overlay, dict) or set(overlay) != {"schema_version", "entries"}
            or type(overlay["schema_version"]) is not int or overlay["schema_version"] != 1
            or not isinstance(overlay["entries"], dict)):
        raise SourceError("invalid German editorial schema")
    by_id = {entry["entry_id"]: entry for entry in entries}
    additions = overlay["entries"]
    unknown = set(additions) - set(by_id)
    if unknown:
        raise SourceError("unknown editorial entry_id: " + ", ".join(sorted(unknown)))

    def clean(value: object, owner: str, maximum: int = 180) -> str:
        if not isinstance(value, str) or len(value) > maximum:
            raise SourceError(f"{owner}: invalid text")
        normalized = _required(value, row=0, column=owner)
        if value != normalized:
            raise SourceError(f"{owner}: text must be trimmed and NFC-normalized")
        return normalized

    positions = {"noun", "verb", "adjective", "adverb", "phrase", "interjection", "particle"}
    grammar_fields = {"article", "plural", "present", "preterite", "perfect", "note"}
    for entry_id, addition in additions.items():
        owner = f"editorial {entry_id}"
        if (not isinstance(addition, dict)
                or set(addition) != {"example", "part_of_speech", "grammar", "accepted_meanings"}):
            raise SourceError(f"{owner}: invalid editorial fields")
        pos = addition["part_of_speech"]
        if not isinstance(pos, str) or pos not in positions:
            raise SourceError(f"{owner}: invalid part_of_speech")
        example = addition["example"]
        if not isinstance(example, dict) or set(example) != {"target", "meaning"}:
            raise SourceError(f"{owner}: invalid example")
        for field, value in example.items():
            clean(value, f"{owner} example.{field}")
        if not re.search("[А-Яа-яЁё]", example["meaning"]):
            raise SourceError(f"{owner}: example meaning must be Russian")
        grammar = addition["grammar"]
        if not isinstance(grammar, dict) or set(grammar) - grammar_fields:
            raise SourceError(f"{owner}: invalid grammar")
        for field, value in grammar.items():
            clean(value, f"{owner} grammar.{field}")
        if pos == "noun" and (grammar.get("article") not in {"der", "die", "das"}
                              or not grammar.get("plural")):
            raise SourceError(f"{owner}: noun grammar requires article and plural")
        if pos == "verb" and not any(grammar.get(key) for key in ("present", "preterite", "perfect")):
            raise SourceError(f"{owner}: verb grammar requires a useful form")
        accepted = addition["accepted_meanings"]
        if not isinstance(accepted, list) or not 1 <= len(accepted) <= 12:
            raise SourceError(f"{owner}: invalid accepted_meanings")
        normalized = [clean(value, f"{owner} accepted_meanings").casefold() for value in accepted]
        if len(set(normalized)) != len(normalized) or by_id[entry_id]["meaning"] not in accepted:
            raise SourceError(f"{owner}: accepted_meanings must retain primary and be unique")
    return additions


def build_documents(path: Path = SOURCE, *, editorial_path: Path = EDITORIAL) -> dict[str, dict[str, object]]:
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
    german = documents["words_de_basic.json"]["entries"]
    additions = load_editorial(editorial_path, german)
    for entry in german:
        if entry["entry_id"] in additions:
            entry.update(deepcopy(additions[entry["entry_id"]]))
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
