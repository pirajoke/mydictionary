# Mini App card-mode simplification

Status: locked 2026-09-17

## Acceptance criteria

- AC-1: The Words tab presents the card trainer before custom-word, device-dictionary, and word-library utilities. All three card modes (mix, review, new) remain visible together.
- AC-2: The trainer exposes one primary start action. Its label and supporting explanation reflect the selected mode, while the mode buttons expose available counts after status loads.
- AC-3: Custom-word actions, the device dictionary, and the word library are progressive disclosures closed by default. Their existing actions, IDs, and deep links remain available after expansion.
- AC-4: The Words tab keeps one orange Lexi selection/action system, uses native accessible controls, and connects the mode group to a visible label and explanation.

## Edge cases

- EC-1: A mode with zero available words remains visible and selectable; starting it keeps the existing explicit empty-state feedback instead of silently switching modes.
- EC-2: The word library remains paginated at six items per page after expansion.
- EC-3: The disclosure layout remains usable at the 320 px project minimum and in RTL locales.

## Constraints

- Preserve the deterministic server-owned queue, rating, resume, undo, and completion behavior.
- Preserve all eight interface locales and Telegram authentication boundaries.
- Do not add dependencies or change database schema.

## Out of scope

- New learning algorithms, new vocabulary sources, or changes to the Telegram bot menu.
- Redesigning the active-card study state.
