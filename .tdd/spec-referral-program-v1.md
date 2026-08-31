# Referral program v1 — locked specification

## Objective

Add a working, privacy-safe referral loop to the Mini App. A learner shares a
personal Telegram deep link. A genuinely new learner may be attributed once,
and the inviter receives AI credits exactly once after that learner completes
onboarding.

## Product contract

- Reward currency is **AI credits**, never Telegram Stars/XTR.
- Reward per qualified referral: **5 AI credits**.
- Reward cap: **10 rewarded referrals per inviter** (50 credits lifetime).
- The invitee receives the existing normal starter allowance only; there is no
  extra invitee reward in v1.
- A referral qualifies when the invitee completes onboarding.
- The Mini App credits tab shows invited count, activated count, earned credits,
  the reward/cap terms, and a primary “Invite friends” action.
- The share action opens Telegram's native share URL with a localized message
  and a personal `https://t.me/<bot>?start=ref_<opaque-code>` link.

## Acceptance criteria

### AC-01 — opaque personal invite

An active learner can request a stable personal invite link from an
authenticated Mini App endpoint. The code is random URL-safe data, does not
contain the Telegram user ID, remains stable across requests, and the server
constructs the URL from the validated configured bot username.

### AC-02 — new-user-only attribution

On the first `/start ref_<code>` request for a previously unknown learner, a
valid code creates exactly one attribution. The persisted acquisition source
and analytics source are the aggregate value `referral`; the opaque code is not
written to analytics or logs.

### AC-03 — abuse and malformed-input rejection

Self-referrals, referrals for an existing learner, a second attribution,
unknown codes, inactive/erased inviters, non-ASCII or malformed payloads, and
oversized payloads are ignored without breaking `/start` or onboarding.

### AC-04 — qualified, idempotent reward

Completing onboarding marks an attribution activated. In the same transaction,
the inviter receives 5 AI credits if fewer than 10 earlier referrals were
rewarded. Repeating or racing the completion cannot duplicate the reward. A
qualifying activation above the cap is recorded with zero reward.

### AC-05 — wallet correctness

Rewarding an inviter with no materialized wallet first preserves the configured
starter allowance, then adds the referral reward. The append-only billing
credit ledger uses a unique referral idempotency key and a referral reference;
no Telegram identifier is placed in the ledger reference fields.

### AC-06 — private aggregate bootstrap

The authenticated Mini App bootstrap exposes only the current learner's
aggregate referral summary: invited, activated, earned credits, reward size and
cap. It does not expose inviter/invitee identifiers, invite codes, usernames,
or another learner's data. Bootstrap remains read-only.

### AC-07 — localized, accessible Mini App surface

All eight supported interface locales include complete referral copy. The
credits tab contains a responsive, keyboard-accessible referral card and a
minimum 44px primary action. The design uses the existing dark/navy dashboard
tokens, clear focus styles, RTL support, and reduced-motion behavior.

### AC-08 — safe failure behavior

If invite issuance fails, the interface does not navigate or share a generic
bot link. It restores the button, shows a localized inline error, and allows a
retry. Duplicate clicks are coalesced while the request is pending.

## Edge cases

- `ref_` with an empty, short, long, or invalid code is treated as a direct
  start for product behavior, while never exposing the submitted token.
- A learner whose first interaction was not the referral `/start` is existing
  and cannot later be attributed.
- Waitlist-mode first starts may be attributed before access approval; reward
  still waits for completed onboarding.
- Invite codes survive normal profile updates and are not returned by bootstrap.
- An erased or blocked inviter cannot accept new attributions.
- Completing onboarding is successful even if no referral exists or the reward
  cap has already been reached.

## Error behavior

- Unauthenticated or invalid Mini App invite requests return the existing
  authentication error contract.
- Inactive learners receive the existing access-denied contract.
- Database failures return a generic temporary-unavailable response without
  leaking identifiers, invite codes, SQL text, or credentials.
- Referral bookkeeping must never prevent the user-facing onboarding completion
  message after the profile completion transaction has succeeded; unexpected
  failures are logged by exception type only.

## Constraints and out of scope

- No gifting, paid subscription, cash value, Stars transfer, or multi-level
  commission in v1.
- No admin referral dashboard and no public leaderboard in v1.
- No device fingerprinting or collection of additional personal data.
- Existing deterministic learning works when AI, Voice, or Stars are disabled.
- Migration revision is `0019_referral_program_v1`, based on
  `0018_interface_locale`.

## Verification commands

```bash
python -m unittest tests.test_referral_program_v1 -v
python -m unittest discover -s tests -v
python -m compileall -q bot.py mydictionary tests
git diff --check
```
