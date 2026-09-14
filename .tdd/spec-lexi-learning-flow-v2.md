# Lexi learning flow v2 — locked 2026-09-14

Owner request: implement the three-release action plan from the product audit.

## Acceptance criteria

- AC1: Main profile starts with a compact learn-now area before calendar/artwork. Current target language and change control are visible. First lesson starts native cards; returning learner resumes a pending session, otherwise reviews available due/mistaken words, otherwise learns new words. Preserve five bottom tabs.
- AC2: Settings names the learning language explicitly. Curated starter words, personal Telegram words and device-local dictionary have clear boundaries. Existing Telegram quick buttons lead to native Mini App destinations when enabled, with existing deterministic bot routes as fallback. Review never silently becomes new/random cards.
- AC3: Authenticated POST /miniapp/api/swipe/status with {} returns counts {new,forgotten,total} and resume metadata or null for the current pack. It does not create sessions, grade words, award XP or emit activity. POST /miniapp/api/swipe/resume with {session_id} returns the original deck cards, current queue/rating counts/undo ID and mode; it does not restart, grade or award XP. Only caller-owned, current-pack, unexpired and unchanged-content sessions are resumable. A pending empty queue can be recovered to finish completion.
- AC4: POST deck keeps fresh-session semantics and existing queue modes. Resume chooses the latest unfinished current-pack session within the existing seven-day lifetime. Sessions in another language remain resumable after switching back. Content enrichment preserves stable vocabulary IDs.
- AC5: Existing replay-safe rating/retry and undo invariants remain. Undo of the last rating after completion is allowed within ten minutes only before a newer session for that user/current pack starts and when word state still matches receipt. Reverse only this session's completion award/counter plus existing rating effects, restore queue, retain audit via swipe_completion_undone (rename prior completion event); completing again emits one current block_completed and awards completion once. Repeated undo/complete retries cannot duplicate counters/events. Expired, foreign, changed-pack/content, stale-word receipts and invalid bodies fail closed.
- AC6: Active card layout hides unrelated library/promotions; reveal/rate/undo reachable at 320x568 and 390x844 with five bottom tabs. Text >= readable supporting scale. New tabs reset scroll; pronunciation has independent error copy and optional IPA disclosure. Examples/grammar appear on reveal, without leaking meaning before recall.
- AC7: Initial auth error offers reopen-in-Telegram, connectivity/service error offers retry; transient card save retries preserve exact operation ID and card. All new UI copy in all eight existing locales; RTL and reduced motion respected. Main action cannot open a different learner's or old pack session.
- AC8: German editorial enrichment starts with 30–50 records, can extend to all100 after review: short target/Russian example, relevant part of speech/grammar and accepted answer alternatives. Canonical enrichment source is versioned and validated by build --check; catalog projects optional grammar safely. Existing target/meaning/entry IDs and progress remain stable; only German pack changes. No unverified CEFR labels or claim of human editorial approval.
- AC9: Privacy-safe versioned swipe_started/swipe_resumed and existing completion events; no raw terms, answers, prompts, names or initData in event properties. Replaying resume should not create duplicate resumed events for the same unchanged state. Existing D1/D7 activity definition remains unchanged, documented as v1 with separate v2 swipe aggregates until a deliberate comparable migration.

## Boundaries / failures

- EC1: Empty review stays empty and offers new words explicitly. Source selection does not merge private/imported and public pack indexes.
- EC2: Feature flags AI/Voice/Stars off do not prevent deterministic cards. Telegram Mini App disabled keeps old bot shortcuts usable.
- ERR1: All new endpoints require signed Telegram identity and active privacy/access; strict exact-body validation, no-store responses and rate limiting follow existing routes.
- ERR2: Delayed responses after language change cannot restore previous pack UI. Undo must not roll back unrelated later profile work.

## Delivery

Backend RED tests: tests/test_miniapp_learning_flow_v2.py. Editorial RED tests: tests/test_german_editorial_v2.py. Browser behavior tests extend public DOM/controller harness; no tests for purely cosmetic reorder. Existing tests asserting superseded exact API fields or frontend flows may be explicitly revised by the test-writing role, never weakened by implementer to force GREEN.

Relevant/full unittest suite, Python compilation, JS syntax, generator check, browser responsive walkthrough, diff review. Keep unrelated research edits out of commit. Human linguistic sign-off and physical Telegram checks must be accurately reported if unavailable, never fabricated.
