# Mini App secondary tabs v2

## Scope

Redesign the Words, AI credits, Languages, and Settings tabs so they share the
clarity, hierarchy, and compact mobile rhythm of the Profile tab. The Profile
tab, authenticated bootstrap, learner data, billing rules, and Telegram deep
links remain unchanged.

## Acceptance criteria

- **AC-1 — Words overview.** The Words tab shows tracked, learned, and due
  counts before the vocabulary list. Word rows separate target, meaning,
  learning state, and correct/wrong attempts without nested generic cards.
- **AC-2 — Credit wallet.** The Credits tab gives the available balance primary
  hierarchy, keeps reserved/spent secondary, explains the one-credit contract,
  and renders every visible one-time product as a structured package row.
- **AC-3 — Honest checkout.** Product rows are actionable only when the existing
  `stars_checkout` feature is true. When it is false, packages remain readable
  but the tab shows one clear unavailable state and never implies that checkout
  succeeded or can be used.
- **AC-4 — Language selection.** The current language is visually distinct,
  language direction and word counts remain visible, and the Telegram change
  action remains the only mutation path.
- **AC-5 — Grouped settings.** Settings are grouped into Learning, Tutor, and
  Features sections, with localized group headings in all eight interface
  locales. Existing values and Telegram actions remain unchanged.
- **AC-6 — Coherent responsive design.** All four tabs reuse the existing local
  section artwork and brand tokens, fit at 320px, preserve 44px touch targets,
  RTL, contrast, keyboard tabs, reduced motion, and empty/error states.

## Edge and error criteria

- **EC-1.** Empty words, zero credits, no products, long localized labels, and
  RTL languages remain readable without fabricated data.
- **ERR-1.** A raw `file://` template is not treated as a supported runtime;
  authenticated Telegram `initData` remains mandatory for bootstrap.

## Constraints

- No new dependency, external image request, data mutation, AI call, invoice,
  payment, or feature-flag change.
- Public Telegram Stars checkout remains disabled until separately enabled by
  its existing production gate.
- Existing Profile tab design and business payload schema remain compatible.
