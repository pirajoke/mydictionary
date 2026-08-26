# Incident log

Append-only, privacy-safe operational history. Never paste credentials, learner
identifiers, messages, prompts, payment IDs, database URLs or raw logs here.

## 2026-08-03 to 2026-08-04 — Telegram token patterns in private HTTP logs

**Severity:** high until token rotation is complete.

**Observed:** 6,380 historical Telegram API token-pattern occurrences in the
private source log. The newest 64 KiB and current OVH container logs contain
zero occurrences.

**Cause:** request-level HTTP logging previously included Bot API request URLs.

**Contained:** verbose request logging was suppressed; an owner-only sanitized
copy was verified with zero matches; token-file loading now rejects unsafe mode,
symlink, malformed and conflicting sources. The source log remains unchanged.

**Open owner gates:** rotate/revoke through BotFather, prove the replacement
heartbeat, then separately approve archival or deletion of the original log.

## 2026-08 — Mac mini outage and OVH migration

**Severity:** high during migration; contained.

**Observed:** the former production host became unreachable. Bot, admin and
PostgreSQL were restored as owner-controlled Docker services on OVH.

**Contained:** GitHub main and production were reconciled to `32ede87`; bot and
admin use the same release; database revision is `0016`; loopback health,
heartbeat and local backup monitor are green; autodeploy is absent.

**Resolved 2026-08-26:** one immutable encrypted off-site object and checksum
were verified, then restored on a separate recovery host into a disposable
PostgreSQL database. Revision `0016_mirror_control_plane_v1` matched, the drill
database was removed, and a private mode-`0600` receipt was written.

## 2026-08-22 — Public hostname has no active tunnel connector

**Severity:** high for the web/admin surface; Telegram learning remains healthy.

**Observed:** public health/login return Cloudflare 1033 while the OVH loopback
origin returns 200. No cloudflared binary, process, unit or container is present
on OVH.

**Cause:** the public tunnel connector was not enrolled after the host move.

**Contained:** application/database changes were stopped; an owner-gated
token-file recovery contract and acceptance/rollback runbook were added.

**Resolved:** a scoped `cloudflared` connector is active on OVH. Fresh public
health and admin-login checks pass while the application origin remains bound
to loopback. No bearer token is recorded in project evidence.

## Entry template

```text
## YYYY-MM-DD — title
Severity:
Observed: aggregate, non-secret evidence only
Cause:
Containment completed:
Open owner gate:
Prevention added:
```
