# Mini App navigation illustrations v2

Status: locked on 2026-08-29.

## AC-1 — recognizable navigation

The five bottom tabs use distinct inline vector illustrations for Profile,
Words, AI Credits, Languages, and Settings. Generic character glyphs are not
used as the visual identity of a tab.

## AC-2 — one coherent MY DICTIONARY style

Every illustration uses the same compact two-tone drawing vocabulary inside
the existing color-coded badge. The selected tab may lift and gain a restrained
halo without changing layout or delaying navigation.

## AC-3 — accessibility and localization

Illustrations are decorative (`aria-hidden`, not focusable); the existing
localized text remains the accessible tab label. Tab roles, roving tabindex,
minimum touch targets, RTL behavior, and reduced-motion support remain intact.

## EC-1 — small and local

Icons are inline SVG with a shared `0 0 24 24` view box. They require no remote
asset, JavaScript dependency, bitmap download, or additional request.

## Out of scope

- No Mini App data, authentication, economics, Stars, AI, Voice, or learner
  record changes.
- No navigation labels, destinations, or tab behavior changes.
