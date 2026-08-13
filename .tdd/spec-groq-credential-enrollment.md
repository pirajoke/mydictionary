# Groq credential enrollment and disabled runtime wiring

## Scope

This change adds a fail-closed way for an authenticated administrator to enroll
one Groq project credential and prepares the existing Groq speech-to-text
adapter for file-based production configuration. It does not enable Voice,
Voice Translation, Telegram Stars, or execute provider requests.

## Credential contract

- AC-GROQ-KEY-01: Groq enrollment is disabled unless
  `GROQ_KEY_ENROLLMENT_ENABLED`, an absolute destination inside
  `DATA_DIR/local-config`, and an expiry no more than one hour away are all
  configured.
- AC-GROQ-KEY-02: The authenticated `/admin/groq-key` form is protected by
  CSRF, accepts only a bounded `gsk_` credential, writes exactly one owner-only
  regular file with mode `0600`, and cannot overwrite files or follow links.
- AC-GROQ-KEY-03: The credential value is never rendered, logged, stored in the
  audit log, or returned after submission. Audit contains only a short SHA-256
  fingerprint and provider identifier.
- AC-GROQ-KEY-04: OpenAI and Groq enrollment windows are independent and the
  existing OpenAI route and configuration remain backward compatible.

## Runtime contract

- AC-GROQ-RUNTIME-01: `GROQ_API_KEY_FILE` must be absolute, owner-owned,
  regular, non-symlinked, no more permissive than `0600`, bounded in size, and
  contain one valid `gsk_` credential without surrounding whitespace.
- AC-GROQ-RUNTIME-02: Direct `GROQ_API_KEY` and `GROQ_API_KEY_FILE` are
  mutually exclusive. Invalid or ambiguous configuration fails before a
  provider object or request is created.
- AC-GROQ-RUNTIME-03: Both Voice Tutor and Voice Translation use the same
  file-loading contract. Disabled features do not require a Groq credential.
- AC-GROQ-RUNTIME-04: The versioned admin launcher forwards only the credential
  file path and boolean configured status; it never reads the key into the
  admin process environment or diagnostics.

## Activation gates

- AC-GROQ-GATE-01: Enabling Groq Voice still requires
  `VOICE_GROQ_ZDR_VERIFIED=true`, a reviewed consent version and notice,
  positive metering, and the existing duration/credit limits.
- AC-GROQ-GATE-02: The default rendered configuration remains Voice=false,
  Voice Translation=false, Stars=false, and ZDR confirmation=false.

## Out of scope

- Merge, production deployment, credential enrollment, credential rotation,
  feature-flag changes, live Groq/OpenAI calls, Telegram invoices, payments,
  refunds, and public launch.
