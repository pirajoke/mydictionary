# Mini App Settings Hub v1

Status: locked on 2026-08-31.

## Product intent

Turn the Settings tab into a compact mobile control center inspired by the
provided reference: a prominent primary action followed by grouped rows with
recognizable color tiles, concise current values, and chevrons. Every row must
open a real MY DICTIONARY workflow; unsupported subscription gifts, voice
selection, voice speed, and an "unlimited" claim are not represented.

## Acceptance criteria

- **AC-1 — Actionable hierarchy.** Settings starts with an AI-credit CTA that
  switches to the existing Credits tab without leaving the Mini App. Below it,
  grouped native buttons expose Invite friends, Dictionary, Learning plan,
  AI tutor, Tutor preferences, Help, and Privacy.
- **AC-2 — Honest current context.** The credit CTA shows the authenticated
  available balance. Dictionary, learning plan, and tutor preferences show
  bounded values from the existing bootstrap payload. AI tutor shows its real
  availability and cannot be launched when the feature is disabled.
- **AC-3 — Real referral reuse.** Invite friends uses the existing authenticated
  referral-invite endpoint, URL validation, coalescing, safe Telegram share,
  loading state, failure state, and retry behavior. Both the Credits and
  Settings entry points stay usable and synchronized.
- **AC-4 — Real Telegram destinations.** The Mini App action contract adds Help;
  `miniapp_help` routes to the existing help command. Settings routes explicitly
  to the existing settings keyboard. Dictionary, AI tutor, and Privacy retain
  their existing allowlisted routes. Unknown deep-link actions never fall
  through to Settings.
- **AC-5 — Localized UI.** New visible labels and accessible names are complete
  and non-empty in en, fr, de, ja, ar, zh, ru, and es. Existing locale switching
  remains an inline, functional control inside the Settings hub.
- **AC-6 — Reference-inspired visual system.** Rows use one coherent local SVG
  icon vocabulary, restrained semantic tile colors, separators, and chevrons;
  the CTA and rows fit 320px, preserve 44px targets, keyboard focus, RTL,
  Telegram light/dark themes, and reduced motion without remote assets or new
  dependencies.

## Edge and error criteria

- **EC-1.** Long translations and unknown/empty setting values wrap safely and
  fall back to the existing localized unknown label; zero credits is shown as
  zero rather than hidden.
- **EC-2.** When Stars checkout is unavailable, the credit CTA still opens the
  honest Credits tab and its existing unavailable state; it never claims
  purchase success or unlimited access.
- **ERR-1.** Referral requests without authenticated Telegram init data remain
  fail-closed. A failed request restores both invite controls and exposes one
  localized retry state without opening an unvalidated URL.
- **ERR-2.** A missing Telegram bridge or bot username causes external actions
  to no-op safely; it never constructs an arbitrary navigation URL.

## Constraints and out of scope

- Preserve the authenticated bootstrap, referral economics, Stars gates,
  learner records, bottom navigation, and current production feature flags.
- No schema migration, new API endpoint, dependency, external image, AI call,
  purchase, invoice, or feature-flag change.
- No gift subscription, paid unlimited plan, voice picker, voice-speed picker,
  or topic preference UI until those product capabilities actually exist.
