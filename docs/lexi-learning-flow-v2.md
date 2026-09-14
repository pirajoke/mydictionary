# Lexi learning flow v2

Native Mini App practice is the primary quick-learning destination. Five bottom
tabs remain. The profile places learn-now and language switching before its
reorderable progress sections. New learners see their lesson before a calendar.

## Entry and continuity

Telegram's existing continue/review/mode/words/language reply buttons open
identity-free Mini App views in private chats when enabled and valid. Disabled
Mini App or unavailable routing preserves existing deterministic Telegram flows.
The `practice` view resumes a pending session, otherwise chooses review when
due/mistaken words exist and new words otherwise. `review` explicitly reviews;
`words` displays choices; `languages` shows the existing pack selector.

`POST /miniapp/api/swipe/status {}` obtains current-pack counts and latest valid
unfinished session metadata without creating study activity or awards.
`POST /miniapp/api/swipe/resume {session_id}` reconstructs the original cards and
current queue for the authenticated learner. Seven-day expiry, active pack,
content fingerprint and privacy/access guards apply. Queues created before v2
lack the reconstruction metadata: they can finish in existing open clients but
are not offered as resumable. Saved word progress remains intact.

Modes retain existing deterministic new/due/mistake selection. Empty explicit
review never silently starts new words. A pause leaves the queue on the server;
no learner cards or authentication data are persisted in browser storage.

## Ratings and completion correction

Lost-response retries reuse the operation identifier. Within ten minutes a
learner can undo the final rating even after completion, provided no newer
session for that pack has started and the word receipt remains current. Undo
reverses only the corresponding rating and completion award/count. It renames
the completion event to `swipe_completion_undone`; completing again creates one
current `block_completed`. Unrelated later profile work is retained.

## UI and content

Active practice hides unrelated word-library/promotional blocks. Grade actions
remain above the bottom navigation, new tabs reset scroll, and IPA is available
through a disclosure beside Listen. Initial authentication and connection errors
offer different recovery actions. New interface copy covers all eight locales.

The renderer supports optional bilingual examples and grammatical forms on the
revealed face. The German enrichment is a separately reviewable editorial draft;
see `docs/german-editorial-review.md` when that content change is present. Machine
checks and agent review do not constitute human linguistic approval.

## Telemetry compatibility

`swipe_started` and `swipe_resumed` carry `version: 2` and bounded metadata only.
Unchanged resume retries do not duplicate the resume event. Existing completion
events retain target-language codes (for example `de`, not storage namespaces).

The existing D1/D7 activity allowlist and window definitions remain version 1.
Report swipe starts/resumes/completions separately until a versioned migration
can compare equivalent cohorts. No terms, answers, names, prompts or initData
belong in these properties. A partial swipe session is not automatically a v1
retention event.

## Validation and rollout

API tests cover identity, exact body validation, rate limits, expiration, content
changes, pack changes, undo, replay and preservation of unrelated progress.
Public controller tests cover resume, queue selection, empty review, completion
undo and late responses after a language change. Browser checks use a synthetic
Flask fixture; real Telegram touch/keyboard behavior and human linguistic review
must be reported separately when not available.

No schema migration is introduced. Rollback uses the prior reviewed image and
the unchanged schema; v2 session metadata is additive. Fresh operational checks
and a verified backup remain required at deployment time.
