# Lexi swipe integration — verification

Base: `d8d98a41b22f5fe236cd57991c5794fb28607c40`.
Branch: `codex/miniapp-swipe-trainer`. Locked spec: `spec-miniapp-swipe.md`.

## Red → Green → Refactor

Independent RED writer: 22 tests, 28 intended failures, zero fixture/import errors.
Additional RED: stale-content rate/undo (200 vs 409) and successive undo (409 vs
200). Server GREEN and separate UI implementation: 24/24 passing. Third-role
refactor extracted only content validation and repeated UI reset helpers;
before/after targeted suite and Node interaction harness remain green.

| Criteria | Passing evidence | Implementation |
|---|---|---|
| AC-1 | deck counts, interleaving, modes, aligned meanings | swipe.py deck |
| AC-2 | SRS interval stages, correct/wrong, XP, level, daily bonus | swipe.py mutate/activity |
| AC-3 | queue head, repeat-once, bounded 1/2-card decks | swipe.py queue transition |
| AC-4 | replay, conflicting IDs, undo/new/existing, stale word, window, stack | swipe.py receipts/freshness |
| AC-5 | empty-queue completion, replay, aggregate analytics | swipe.py completion |
| AC-6 | unchanged nav, real cards, reveal, speech, buttons, gestures, undo, summary | template + miniapp-swipe.js |
| AC-7 | 8 locales, auth, failed request/replay, keyboard, focus, wrapping | UI assets + Node/browser checks |
| EC-1/2/3 | empty/short queues, upgrade/downgrade, erasure/retention, content reorder | API + migration + privacy |
| ERR-1/2 | strict payloads, disabled/auth/access, ownership, pack/expiry, limits/storage | signed Flask routes |

Tests: `tests/test_miniapp_swipe_v1.py` and `tests/browser/miniapp-swipe.cjs`.
Neighbor schema assertions intentionally advance to 0023. The dashboard script
allowlist admits only the reviewed new same-origin module; four injected
external/unreviewed scripts still fail its assertion.

## Final local checks

- Full unittest discovery: **1121 tests, OK, 3 PostgreSQL-only skips** (47.728s).
  Isolated DATA_DIR prevents modifying the owner's existing legacy local SQLite
  database. The initial default-directory run's 17 errors were legacy local
  database revision errors, not source or production migration failures.
- Python compilation, both JS syntax checks and staged diff whitespace: pass.
- Secret-pattern scan: 26 staged source/test/document files, zero findings.
- Real Chromium + Flask + synthetic learner, no production data/provider calls:
  390×844 mobile and 1280×900 desktop, reveal and persisted grade/undo, zero page
  errors and no horizontal overflow. Arabic/dark 320px check also passes, with
  physical left Again/right Know preserved.
- Browser simulations: 400/401/403/404/409/429/503 UI branches pass. Retryable
  failures retain the card and block new ratings; auth failures close writes;
  stale sessions offer fresh practice without losing saved progress.

## Findings and release boundary

CRITICAL: none. Completeness/traceability/coherence: passing for the locked spec.
WARNING: native Telegram WebView device audio/gesture acceptance still requires
a real device; speech is optional and disabled when unavailable. Browser/VM
checks do not prove every OS WebView implementation.

Migration is additive (`0023_miniapp_swipe_sessions`); existing learning tables
are untouched structurally. After migration, rollback is disable/fix-forward,
not automatic downgrade/older-code activation. Production evidence belongs in
the separate release receipt, after fresh backup and live checks. Unrelated
research changes are excluded from delivery.
