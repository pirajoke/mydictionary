# Lexi native Telegram learning — local candidate

Status: local implementation only. No push, merge, production deployment, real
learner mutation or Telegram learner message is authorized for this candidate.
Production facts recorded elsewhere apply to the previous release, not this code.
German editorial PR #143 is excluded and still requires human review.

## Observable contract

Active path: registered reply/callback handlers → `auth` → existing native block
handlers → `bot_learning.rate` → canonical SRS/profile transaction. The defect was
an enabled-Mini-App routing shortcut bypassing these handlers; block state was
RAM-only and summary formatting awarded completion again on every display.

- `/start` first sends the persistent keyboard and a compact personal text with
  selected language and due count. A second native inline message offers start or
  continue. No banner upload blocks either action.
- Primary reply controls: Continue; Review / Add words; My words / Language.
  Existing delivered labels remain recognized. Only explicit Swipe and `/app`
  launch the separate Mini App.
- Continue resumes the current compatible incomplete native block. Review uses
  due words and does not silently substitute a random new lesson when empty.
- My words opens native topics, current-word mode selection and existing custom
  vocabulary practice. Add uses the existing manual-pair capture/import flow.
  This is not a new custom-vocabulary storage or swipe engine.
- Changing mode or viewing selected cards does not rewind accepted answers.
  Selecting a new topic/lesson or retrying mistakes explicitly starts an attempt.
- Completion has at most three primary buttons: retry mistakes (or another lesson
  when none), finish/home, More. More contains AI, voice and other advanced routes.

## Persistence and shared progress

Additive migration `0024_bot_learning_sessions` adds one bounded native-session
row per learner/pack. It stores an allowlist of indices, position, mode, counters,
short callback token, completion flags, content digest and issued SRS snapshots;
no vocabulary text, user messages, prompts or authentication data.

Authenticated updates restore the current pack's compatible block. Explicit
standalone written/smart practice keeps its pending answer state. Expired or
editorially incompatible native state is not advertised as resumable. New
session-bound keyboards and questions are saved before Telegram network I/O.
An acknowledged stale-save refusal prevents delivery of an unrecorded new token.

Native ratings use the same `WordProgress` / `UserProgress` as Mini App swipe.
One transaction locks the learner/profile and word, checks issued position/token
and SRS snapshot, applies the existing SRS schedule and fresh aggregate XP, then
advances the block and rotates the callback token. Final answer and the existing
25-XP session bonus commit together exactly once. Redisplaying summary is pure.
Native written answers also retain up to 256 recent Telegram update receipts per
pack, internally and without message text, so redelivery cannot grade the next
card. A genuinely new update remains a new answer; older evicted receipts are not
an unlimited history or a universal deduplication guarantee.
No claim is made that chat and swipe share an identical session or queue.

If swipe changes an issued native word, its stale chat rating is rejected without
extra XP. Explicit Continue reissues only remaining words with fresh snapshots.
Conversely, swipe Undo refuses to overwrite a later native rating. Fresh deliberate
practice in separate sessions may legitimately rate a word again.

Sessions expire after seven days and are included in retention and learner erasure.
Switching language preserves per-pack native blocks; old pack buttons are stale in
the new selected pack. AI/Voice/Stars remain optional to deterministic learning.

## Verification and phone acceptance

Synthetic SQLite tests cover actual authenticated restore/save and handlers,
restart, pack switching, mode continuity, stale/repeated buttons, completion once,
fresh XP merge, both cross-surface conflict directions, access/content/expiry,
standalone written practice, erasure and retention. Old launcher-only expectations
are updated intentionally, without weakening the reproducing native tests.

Local verification on 2026-09-15: full suite 1174 tests, green with three local
PostgreSQL-only skips; focused native/block/swipe suite 99 tests, green; compilation
and `git diff --check` green. No new dependencies or German content changes.
Current candidate PostgreSQL/CI and physical phone acceptance are still release
gates, not implied by SQLite success or earlier release CI.

Before release approval, test on a separate physical Telegram test profile:
start and persistent controls; resume after bot restart; language switch/back;
topic/custom selection and manual add; flash/quiz/type; mistakes retry and More;
double callback; swipe-changing an issued word; network interruption; narrow/RTL
screen and first/repeated Mini App image loading. Test answers change that profile.

Mini App banners already use five WebP preloads/eager requests and immutable cache
in the existing release; this candidate additionally removes chat start's blocking
image upload. There is no controlled device baseline for a numerical speed claim.

## Release and rollback boundary

Published release base: `83ecd4c3bc908c9c309619fd0dad7541df5dbf7f`.
Local documentation base: `956faa8`; candidate branch:
`codex/native-chat-learning-20260915`. The preceding documentation packet is local
and unpublished too. No German content/generator/catalog changes are included.

Deployment, if separately approved, must apply additive migration 0024 before
running the candidate and freshly verify production health, schema, heartbeat,
backup and flags. A code rollback to the published base can leave the extra table
in place; do not restore/rewind learner progress merely to roll back UI. Dropping
0024 intentionally removes only native-session continuity, not shared SRS/XP, and
is not necessary for a normal code rollback.
