# Locked specification: admin password recovery and Google sign-in

Status: LOCKED
Owner goal: add email password reset and Google sign-in to the protected MY DICTIONARY admin console.
Scope: the singleton administrator only. This does not add learner web accounts, signup, social-account linking, or public user authentication.

## Observable acceptance criteria

### AC-1 — Login surface and disabled state

- Password login remains available and unchanged.
- When email recovery is fully configured, `/admin/login` shows a password-reset link and `/admin/forgot-password` is available.
- When Google sign-in is fully configured, `/admin/login` shows a Google sign-in action and `/admin/google/login` is available.
- When a feature is entirely unconfigured, its UI and route are unavailable without leaking configuration details.
- A partially configured, unsafe, or contradictory auth feature fails closed during app startup.

### AC-2 — Password-reset request

- The request form is CSRF-protected and rate-limited per request source.
- The submitted email is stripped and case-folded before an exact match against the one configured administrator email.
- Matching and non-matching addresses receive the same generic response, status, and visible copy.
- A matching request creates a cryptographically random token, persists only an HMAC-SHA256 digest and bounded metadata, invalidates any older pending reset, and sends one link constructed from the configured trusted public URL.
- The raw token is present only in the outgoing reset link. Raw token and administrator email never enter database audit details, HTTP responses, application logs, or persisted reset rows.

### AC-3 — Password-reset completion

- A valid, unexpired, unused token opens the reset form.
- A matching password confirmation of at least 12 characters updates the Werkzeug password hash, marks the token consumed, increments the admin session version, and invalidates all existing admin sessions.
- A token is single-use. Unknown, expired, superseded, or consumed tokens produce one generic invalid-link response and no credential mutation.

### AC-4 — Google authorization start

- Google sign-in uses Authorization Code + OpenID Connect with `openid email`, an exact configured client ID, a callback derived only from the trusted public URL, and cryptographically random state and nonce.
- State and nonce are stored only in the signed admin session and replaced on every start.
- Client secrets never appear in redirects, query strings, logs, templates, or persisted records.

### AC-5 — Google callback and identity validation

- Callback state is required and compared in constant time, then consumed once.
- The authorization code is exchanged once with a bounded timeout and no automatic retry.
- The returned ID token is validated for exact audience, allowed Google issuer, future expiry, exact nonce, verified email, and exact normalized administrator email.
- Successful validation creates the normal admin session using the current credential username and session version.
- Access, refresh, and ID tokens are never stored. Authentication or provider failures create no admin session and expose only generic failure copy.

## Edge cases

### EC-1 — Repeat reset requests

- Issuing a new reset invalidates every older pending token atomically.

### EC-2 — Uniform account-discovery response

- Unknown, differently cased, or whitespace-padded email input cannot reveal whether the address is configured; only the exact normalized owner email can trigger mail delivery.

### EC-3 — Fixed post-auth destinations

- Google and reset success redirect only to the fixed admin index. User-controlled return URLs and open redirects are not supported.

### EC-4 — OAuth cookie compatibility

- The admin session cookie is `HttpOnly` and `SameSite=Lax` so the top-level Google callback retains state; production keeps `Secure=true`. Existing CSRF checks remain mandatory for every state-changing POST.

## Error behavior

### ERR-1 — Mail delivery failure

- A mail failure leaves no usable reset token, returns generic request copy, and emits only a privacy-safe audit action.

### ERR-2 — Throttling

- Excess reset requests return `429`, send no mail, and create no reset record.

### ERR-3 — OAuth failure

- Missing/mismatched state, missing code, bad JSON, network failure, invalid token claims, or denied identity produce no login and no token persistence.

### ERR-4 — Secret-file safety

- Google client-secret and SMTP password files must be absolute, regular, non-symlink, owned by the current process user, mode `0600` or stricter, non-empty, and bounded in size. Unsafe files fail startup.

## Constraints and non-goals

- No public signup, learner accounts, passwordless email login, account linking, refresh-token scope, or Google-token persistence.
- SMTP uses TLS and an authenticated account. The application does not provide an insecure plaintext-mail fallback.
- Reset token lifetime defaults to 15 minutes and must remain within 5–60 minutes.
- Configuration is optional as a complete feature set: absent means disabled; partial means startup failure.
- Deployment may ship both features disabled. Live activation requires protected provider credentials and a verified callback URL; no provider account or secret is invented by code.
- Security audit details contain action metadata only, never raw email, reset token, OAuth code, charge data, or provider tokens.

## Required verification

- Focused behavioral tests for every criterion and error path.
- Migration upgrade and model/store tests on SQLite plus PostgreSQL-compatible schema review.
- Existing admin authentication, CSRF, limiter, security-header, launcher, and health tests.
- Full unittest suite, `compileall`, `git diff --check`, secret/private-data diff scan.
- PR CI, production migration/deploy/restart, privacy-safe health probe. Live Google/SMTP activation is separate unless protected credentials are already present and valid.
