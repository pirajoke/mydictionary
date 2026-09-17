# Dictionary learning profile v1

Status: locked 2026-09-17

## Acceptance criteria

- AC-1: The public dictionary leads with a device-scoped learning profile before search and word results. It reports saved words, locally learned words, words due now, and distinct study days without implying access to Telegram account data.
- AC-2: The profile visualizes the last seven local study days and current streak from bounded browser storage. Saving a word and answering a practice card record local activity.
- AC-3: The default dictionary view renders at most eight results and exposes one `Show more` action. Search, saved-only view, language changes, and clear reset pagination without breaking reverse or Unicode lookup.
- AC-4: The profile offers a print/PDF snapshot. CSV, offline installation, standalone HTML download, and their explanatory copy remain available inside one collapsed `Export and offline` disclosure.
- AC-5: The online and standalone dictionary use the same dependency-free profile calculations, accessible labels, existing Lexi palette, and responsive/print layouts.

## Edge cases

- EC-1: Empty or legacy `lexi:dictionary:v1` storage produces a useful zero-state profile and keeps search/practice working.
- EC-2: Malformed activity dates/counts are ignored; retained activity is bounded to the most recent 400 days and counts are bounded integers.
- EC-3: A downloaded dictionary remains self-contained, CSP-hashed, printable, searchable, and usable without network access.
- EC-4: The public route continues to project only redistribution-approved starter packs and never reads learner/database state.

## Constraints

- Do not expose Telegram profile or progress through the unauthenticated `/dictionary/` route.
- Do not add runtime dependencies, database schema, remote analytics, or network calls for profile calculations.
- Preserve all existing search, save, written practice, CSV, service worker, download, CSP, and language-pair contracts.

## Out of scope

- A public shareable Telegram learner profile.
- Server-generated PDF files or cross-device synchronization.
- Changes to spaced repetition in the authenticated Telegram/Mini App product.
