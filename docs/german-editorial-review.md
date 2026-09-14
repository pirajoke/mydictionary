# German starter editorial draft

Status: machine-authored editorial draft, 2026-09-14. No human linguistic
sign-off has been obtained. This is not a claim of CEFR certification or review
by Duden. Examples and Russian translations are original text written for this
project; dictionary examples have not been copied.

## Scope and reproducibility

The canonical additive source is `content/german_editorial.json`, schema version
1. Its 100 records project into the German starter pack, content version 2.
Every record has a short German/Russian example, part of speech, grammar object
and an accepted-meaning list that retains the original primary meaning. There
are 45 records with additional accepted meanings. All ten verbs have present,
preterite and perfect forms. Nouns have article and plural information; the
beginner-facing `meist Singular` marker describes normal mass-noun usage, not
the absence of every possible plural.

Run `.venv/bin/python scripts/build_basic_packs.py` to regenerate, or add
`--check` for a read-only reproducibility check. The generator rejects unknown
IDs, identity-field overrides, malformed examples/grammar, unsafe Unicode and
accepted meanings that omit the primary. The catalog validates optional
grammar again at load time and copies nested dictionaries on read.

The aligned TSV remains the authority for targets, primary meanings and entry
IDs. Tests lock those German fields against the base fingerprint and lock all
six other generated language packs in their entirety. Progress IDs remain
derived from the same pack ID and entry ID. The German content-version increase
marks an editorial revision, not a vocabulary identity migration.

## Review performed and remaining limitations

An automated structural pass and a manual agent review covered all 100 records
after drafting. This allowed extension from the initial starter-sized scope to
all 100 in this change; it is not human editorial approval. Accepted variants
include common Russian synonyms, familiar registers (мама/мать), and precise
equivalents of broad existing labels. They are not a general synonym engine.

Existing primary-label distinctions are preserved and explained rather than
silently changing learner identities or the aligned source:

- `Hand` names the hand, not the whole arm. Accepted `кисть руки` and a grammar
  note clarify the existing broad `рука` label.
- `Vormittag` means the part of the day before noon. The existing `утро` remains;
  `первая половина дня` and the example provide a more precise equivalent.
- `Straße` is usually a street or surfaced road; `Bahnhof` is a railway station.
- `es tut mir leid` expresses regret/apology; the preserved `простите` is an
  apology rendering, while `мне жаль` supplies a closer phrase translation.
- `Medizin` uses its medication sense here, not the academic discipline.

A German/Russian-speaking human should review naturalness, accepted-answer
boundaries, grammatical labels and examples before any claim of linguistic
approval. These checks do not certify the unchanged IPA or all original
primary translations. The notes identify known broad mappings for a separate
content-policy decision if stricter sense matching is wanted.

## Primary reference checks

Consulted on 2026-09-14 for specific grammatical facts and sense distinctions:

- [Duden: Buch](https://www.duden.de/rechtschreibung/Buch): neuter noun and
  plural `Bücher` (checked in the parent task).
- [Duden: Wasser](https://www.duden.de/rechtschreibung/Wasser): neuter noun;
  both `Wasser` and `Wässer` occur as plurals in specific uses.
- [Duden: Milch](https://www.duden.de/rechtschreibung/Milch): feminine noun;
  specialist plurals `Milche`/`Milchen` exist.
- [Duden: Medizin](https://www.duden.de/rechtschreibung/Medizin): medication
  sense and plural `Medizinen`; the discipline sense has no plural.
- [Duden: Herz](https://www.duden.de/rechtschreibung/Herz): neuter noun,
  ordinary genitive/dative `Herzens`/`Herzen`, plural `Herzen`.
- [Duden: zuhören](https://www.duden.de/rechtschreibung/zuhoeren): separable
  verb forms `hört zu`, `hörte zu`, `hat zugehört`.
- [Duden: Vormittag](https://www.duden.de/rechtschreibung/Vormittag): time
  period before noon.
- [Duden: Student](https://www.duden.de/rechtschreibung/Student): masculine
  noun with weak inflection.

References verify selected facts only. They do not endorse the pack or the
Russian answer variants. No CEFR labels are introduced.
