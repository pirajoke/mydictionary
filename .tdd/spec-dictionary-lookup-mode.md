# Dictionary lookup mode

## Goal

Add an explicit Telegram `/dictionary` mode. A learner types a word or short
phrase and Lexi returns the curated translation from the learner's currently
selected vocabulary pack.

## Acceptance criteria

- **AC-1 — Direct lookup.** `/dictionary <query>` performs a case-insensitive,
  Unicode-normalized exact lookup in the active pack. It accepts either the
  target term or one of the learner-language meanings and returns one compact
  localized dictionary card with target flag/term, transcription when present,
  and meaning flag/translation.
- **AC-2 — One-shot mode.** `/dictionary` without a query asks for one word or
  short phrase and stores only a bounded expiry marker. The next eligible text
  is consumed once, the marker is removed before processing, and a second text
  follows the normal Mirror route.
- **AC-3 — Honest miss.** A missing or invalid query returns a localized message
  that the word is absent from the selected dictionary and points to `/ai` as
  the explicit optional fallback. A miss never calls an AI provider, reserves
  or spends AI credits, or mutates word progress.
- **AC-4 — Native discovery.** `/dictionary` is registered in polling and appears
  in the localized Telegram command menu for all eight supported interface
  locales.

## Edge cases

- **EC-1.** Queries are stripped, single-line, and bounded to 80 Unicode code
  points. Empty, oversized, or multiline input fails closed without lookup.
- **EC-2.** Pending mode expires after ten minutes. Expired or malformed state
  is removed and returns the localized stale prompt without calling Mirror or
  AI.
- **EC-3.** Active written-answer exercises retain priority over dictionary
  pending state, so learning answers are never stolen by the lookup mode.
- **EC-4.** Matching is deterministic. If aliases collide, the earliest curated
  entry in the active pack wins; no fuzzy or generated translation is invented.

## Error handling

- **ERR-1.** No active/visible pack returns a localized unavailable response;
  no exception or private catalog detail is exposed.
- **ERR-2.** Dictionary rendering is plain Telegram text and bounded below the
  Telegram message limit.

## Constraints

- Deterministic cards, quizzes, written practice, pronunciation, and spaced
  repetition remain unchanged.
- Lookup is free and local to the downloaded/current curated pack.
- Unknown words may be sent to `/ai` only through the existing explicit AI
  flow; dictionary mode itself never triggers a paid request.
- Do not persist the raw lookup query in database records, analytics, logs, or
  pending state.

## Out of scope

- Exporting or downloading a dictionary file.
- Fuzzy search, external dictionary APIs, or background catalog expansion.
- Adding dictionary lookup to the Mini App in this cycle.
