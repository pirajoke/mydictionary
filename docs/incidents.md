# Incident log

This append-only log records security and operational incidents without
credentials, learner identities, messages, private paths, or raw logs.

## 2026-08-03 to 2026-08-04 — Telegram token present in private HTTP logs

**Severity:** high until rotation is complete.

**Observed:** the private mode-`0600` bot log contained 6,380 historical
Telegram API URL token-pattern occurrences. The newest 64 KiB contained zero
occurrences after HTTP client logging was suppressed.

**Cause:** request-level HTTP logging included Telegram Bot API request URLs.

**Containment completed:**

- verbose HTTP request logging was suppressed;
- admin and autodeploy logs were verified with zero token-pattern occurrences;
- a separate mode-`0600` sanitized copy was created and verified with zero
  remaining token-pattern occurrences;
- the original source log was retained unchanged for separately approved
  cleanup.

**Still open:**

- move the current production token from the legacy configuration source into
  the protected `BOT_TOKEN_FILE` flow;
- prove heartbeat and local/public health using the still-valid token file;
- separately rotate/revoke the historically exposed token through BotFather;
- verify polling again with the replacement token;
- archive or delete the original source log only under a later explicit cleanup
  approval.

**Prevention added:**

- owner-only token-file loader with strict file, mode, symlink, format, and
  conflicting-source checks;
- privacy-safe log audit and append-only sanitized-copy tooling;
- runbook ordering that separates reversible file cutover from irreversible
  BotFather rotation and later source-log cleanup;
- repository-level credential and external-action gates in `AGENTS.md`.

## Incident entry template

```text
## YYYY-MM-DD — short title
Severity:
Observed: aggregate, non-secret evidence only
Cause:
Containment completed:
Still open:
Prevention added:
Owner-gated follow-up:
```

Never paste raw logs, environment output, credentials, Telegram request URLs,
learner identifiers, messages, prompts, answers, database URLs, payment IDs, or
private recovery material into this file.
