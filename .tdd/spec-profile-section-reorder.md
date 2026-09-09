# Profile section long-press reorder

## Scope

Allow a learner to personalize the order of the large blocks on the Mini App
profile tab. The bottom navigation and all other tabs stay fixed. The order is
stored locally for this Telegram Mini App installation; no learner identifier
or profile data is written to browser storage.

## Acceptance criteria

- **AC-1 — Reorderable profile structure:** Every large top-level profile block
  has one stable allowlisted key inside one ordered layout container. The
  existing initial order, content IDs, controls, and actions remain unchanged.
- **AC-2 — Long-press drag:** A primary pointer held still on a profile block for
  420 ms starts reorder mode, lifts only that block, produces Telegram haptic
  feedback when available, and lets pointer movement place it before or after
  another allowlisted block.
- **AC-3 — Durable order:** Dropping a moved block serializes only the validated
  allowlisted key order. A later Mini App load restores that order before the
  profile is presented.
- **AC-4 — Keyboard parity:** A focused profile block moves with Alt+ArrowUp or
  Alt+ArrowDown, saves the order, and announces the new position through a
  polite live region.

## Edge and error criteria

- **EC-1 — Native controls remain native:** A quick press never reorders. A
  pointer moving more than the gesture tolerance before 420 ms cancels the
  long press. Nested buttons, links, inputs, selects, textareas, and summaries
  keep their normal tap behavior. A top-level action block may still be held to
  reorder, and its click is suppressed only after an actual long press.
- **EC-2 — Safe persistence:** Missing, unavailable, malformed, duplicated,
  unknown, or partial local storage data cannot remove or duplicate a block.
  Known saved keys are restored first and every missing current key is appended
  once in default order.
- **EC-3 — Clean cancellation:** Pointer cancel, lost capture, tab change, and
  page hide clear timers and visual drag state without saving an unintended
  move.
- **EC-4 — Accessible motion:** Reorderable blocks are keyboard focusable,
  receive localized assistive instructions, have a visible focus treatment,
  and reorder transitions respect `prefers-reduced-motion`.

## Constraints

- No new dependency.
- No server schema or API change.
- No Telegram identifier or learner profile content in local storage.
- Existing profile content, IDs, calendar controls, deep links, and localization
  behavior must remain intact.

## Out of scope

- Reordering blocks on non-profile tabs.
- Cross-device synchronization of the personalized order.
- Editing the contents inside a block.
