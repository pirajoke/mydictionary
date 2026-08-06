# Pilot Operations

The `Pilot` admin tab is the operational view for the controlled learner
cohort. It is intentionally separate from the product and commercial funnels.

## Cohort and stages

The selected cohort contains learner accounts with a `pilot_waitlist_joined`
event during the selected 30-day window. Admin accounts are excluded.

Stages count distinct cohort users who reached each durable event:

1. `pilot_waitlist_joined`
2. `pilot_access_approved`
3. `onboarding_completed`
4. `block_started`
5. `block_completed`

The participant filter uses current access and onboarding state, but only a
`block_started` event recorded after the learner joined the pilot can move that
learner from `first_block` to `engaged`. Historical sessions cannot inflate the
pilot activation view.

Access changes write the audit log, lifecycle event, and notification outbox
entry in the same database transaction. A failed transaction therefore cannot
grant access without recording the corresponding operational work.

## Retention

`D1` and `D7` use calendar windows relative to each learner's first waitlist
event. A learner is eligible only after the complete day boundary has passed.
Retention counts at least one allowlisted product activity from hour 24 to 48
for D1, or hour 168 to 192 for D7. The admin view always displays both the
retained and eligible counts next to the percentage.

## Notification outbox

Approving a learner queues the fixed `pilot_access_approved` notification.
The bot leases due rows and delivers them with at-least-once semantics:

- PostgreSQL workers use `FOR UPDATE SKIP LOCKED`.
- Leases expire after 60 seconds so interrupted work can be reclaimed.
- Temporary failures use bounded exponential backoff and stop after five tries.
- Blocking a learner cancels queued approval notifications.
- Delivery logs contain error classes and status only, never user IDs or text.
- Account erasure deletes all notification rows for that learner.

At-least-once delivery means a process crash after Telegram accepts a message
but before the database commit can produce one duplicate. The fixed copy is
non-sensitive and the outbox never stores arbitrary message content.

## Rollout

This change does not alter `BOT_ACCESS_MODE`, enable payments or AI, send
notifications during tests, merge code, or deploy production. Production
activation requires the normal migration-aware release process and a separate
deployment approval.
