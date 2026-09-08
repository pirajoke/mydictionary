# AI Tutor / commerce separation

Status: locked

## Acceptance criteria

- AC-1: Opening `/ai` shows only the localized AI Tutor introduction and learning actions. It does not load or display the balance, billing policy, product catalogue, prices, or purchase buttons.
- AC-2: The Tutor screen includes one localized secondary action that opens a separate credits-and-plans screen.
- AC-3: The credits-and-plans screen shows the localized AI-credit balance, billing policy, available product catalogue, and purchase buttons when checkout is enabled. It does not show Tutor learning actions.
- AC-4: The credits-and-plans screen includes a localized action that returns to the Tutor screen.
- AC-5: With an active learning block, the Tutor screen preserves the four contextual actions: vocabulary, mistakes, progress, and ask a question.
- AC-6: Without an active learning block, the Tutor screen preserves ask-a-question and start-lesson actions.
- AC-7: All new visible labels and headings are localized for every supported UI locale.

## Edge and error criteria

- EC-1: When checkout is unavailable, the credits-and-plans screen remains readable, shows the balance and policy, exposes no purchase callback, and explains that purchase is unavailable.
- ERR-1: If the balance cannot be loaded, the credits-and-plans screen displays the existing localized unavailable-balance state.
- ERR-2: If the catalogue cannot be loaded, the credits-and-plans screen remains usable and does not expose purchase callbacks.

## Constraints

- The deterministic lesson and review flows remain unchanged.
- Existing `buy:<product_id>` callbacks and billing validation remain unchanged.
- No new dependency or database migration is introduced.
- The persistent reply keyboard at the bottom of Telegram is out of scope; this change affects the inline Tutor and commerce messages only.
