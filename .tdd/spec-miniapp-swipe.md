# Mini App swipe trainer — locked specification

Base: d8d98a41b22f5fe236cd57991c5794fb28607c40. Scope: curated vocabulary,
inside the existing Words panel. Approved Lexi demo is the visual reference.

## Public API and persistence

All endpoints require enabled Mini App, signed X-Telegram-Init-Data and active,
non-erased learner. POST JSON uses exact keys. No AI/Voice/Stars dependency.

- POST `/miniapp/api/swipe/deck`: `{mode}` (mix, forgotten, new).
  Returns `{session_id, pack_id, language, tts_locale, mode, cards, queue,
  counts}`. Cards contain word_index, target, meaning, transcription and kind.
  Queue contains word indices. Counts contain new, forgotten and total pool sizes.
- POST `/miniapp/api/swipe/rate`: `{session_id, operation_id, word_index, knew}`.
  UUID IDs, exact boolean knew, non-boolean integer index. Returns session_id,
  queue, reviewed, known, again and undo_operation_id. Operation replay is safe.
- POST `/miniapp/api/swipe/undo`: `{session_id, operation_id}`. Same state response.
- POST `/miniapp/api/swipe/complete`: `{session_id}`. Returns completed=true,
  reviewed, known, again and earned_xp (answer XP plus 25 session XP).

Use one new `miniapp_swipe_sessions` table, Alembic head
`0023_miniapp_swipe_sessions`, storing owner, public pack ID, progress namespace,
initial indices and bounded rating/queue state JSON (no terms or messages),
creation time and completion time. Sessions expire after seven days and are
deleted by learner erasure and retention cleanup. Existing learning data survives
upgrade. Downgrade removes only the new table. Schema-head assertions may be
updated by RED writer because the schema intentionally advances.

## Acceptance criteria

- AC-1: Deck uses the learner's active visible, compatible pack and native-language
  meanings. New = untracked/no actual ratings. Forgotten = due OR wrong_count>0
  and correct_count<3. Due words sort first, then mistakes, in stable pack order.
  Maximum ten cards. Mix selects up to seven forgotten and three new, fills
  shortages and interleaves two forgotten then one new. Counts describe pools,
  not only selected cards. No learned non-due fillers and no custom-word mixing.
- AC-2: Rate persists exact bot SRS intervals [1,3,7,14,30,60], correct_count +1
  on know; wrong_count +1 and correct_count max(0,n-1) on again, interval one day.
  Adds total correct/wrong, 10/2 answer XP, canonical level thresholds and daily
  activity/streak bonus. Transactions lock owner/profile/session/word consistently.
- AC-3: Session queue is authoritative. Again reinserts the card after two other
  cards once; a second again finishes that card. Know removes it. Only the queue
  head can be rated. Response reports actual ratings and latest undo operation.
- AC-4: Identical operation replay returns current session state without further
  SRS/XP changes; conflicting reuse is 409. Undo latest rating within ten minutes
  restores previous word state (or removes newly tracked row), queue and answer
  totals/XP, but retains earned daily activity/streak. Undo is idempotent. An
  intervening answer to the same word causes 409, never overwrites newer progress.
- AC-5: Complete requires empty queue, is idempotent, increments sessions and adds
  25 XP once, and records privacy-safe block_completed analytics with source
  miniapp. Completed sessions cannot be rated or undone.
- AC-6: UI in Words has mix/forgotten/new, flip/reveal, pronunciation via device
  speech when available, left again/right know, equivalent buttons, undo and
  completion summary. Uses returned real cards and persists each assessment.
  Existing five-item bottom navigation remains byte-for-byte unchanged.
- AC-7: UI copy is localized for all eight supported locales. Existing Lexi tokens,
  readable IPA, responsive widths, keyboard operability, focus and reduced motion
  are preserved. Loading, empty, offline/error and disabled/auth states are visible;
  no advance/score on failed requests; retry reuses operation ID. Text uses safe
  DOM textContent, no learner content in HTML injection or localStorage.
  Neighboring dashboard cosmetic-only script allowlist intentionally gains the
  reviewed same-origin miniapp-swipe.js module; unreviewed/external scripts remain
  prohibited. Historical stylesheet cache prefix stays, with a new release suffix.

## Boundaries and errors

- EC-1: Empty mode pool returns empty cards/queue and no session; completion never
  grants XP for empty practice. One/two-card queues and repeat/undo are bounded.
- EC-2: Migration is additive, retention removes expired sessions, erasure removes
  all owned sessions without deleting another learner's session.
- EC-3: A content update/reorder after deck issuance must not retarget a saved
  index to a different word. Reject stale sessions with 409 before rate/undo.
  Store only content progress IDs as internal comparison metadata, no raw terms.
- ERR-1: Disabled=404; absent/invalid/expired auth=401; inactive/erased=403; unavailable
  owned session=404; malformed JSON/extra keys/mode/UUID/type/index=400; expired,
  changed active pack, invalid queue transition or completed mutation=409;
  throttled=429; storage failure=503. APIs are no-store and use protected auth,
  exempt only these specific signed POST routes from admin CSRF.
- ERR-2: Cross-owner IDs never disclose or mutate another learner's data. Hidden,
  incompatible or missing packs cannot issue/rate cards. Stale pack switches do
  not write progress into a different namespace.

## Out of scope

No bottom-navigation redesign, Telegram keyboard redesign, AI-generated content,
custom word SRS rewrite, font substitution in Telegram itself or analytics UI.
