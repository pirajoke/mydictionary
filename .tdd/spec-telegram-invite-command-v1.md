# Telegram invite command v1

Status: locked on 2026-09-01.

## Product intent

Add the reference-inspired two-step Telegram invite entry: `/invite` first
explains the real MY DICTIONARY referral benefit, then a single Continue button
opens Telegram's native share composer with the learner's personal referral
link. Keep the existing one-tap Mini App referral action unchanged.

## Acceptance criteria

- **AC-1 — Discoverable command.** The bot registers `/invite` and includes it
  in the localized private command menu when the Mini App/referral surface is
  enabled.
- **AC-2 — Honest localized offer.** An active, onboarded learner receives
  localized copy in all eight supported interface locales. The copy states the
  real terms: 5 AI credits after an invited friend completes onboarding, with a
  maximum of 10 rewarded referrals. It never promises unlimited access, a gift
  subscription, Telegram Stars/XTR, cash, or a reward for the invitee.
- **AC-3 — Reference-inspired continuation.** The response contains one
  localized Continue URL button. Its destination is Telegram's HTTPS native
  share endpoint and includes both localized share text and the learner's
  personal `https://t.me/<configured-bot>?start=ref_<opaque-code>` link.
- **AC-4 — Stable private referral reuse.** `/invite` reuses
  `DatabaseStore.issue_referral_code`; repeated commands keep the same personal
  deep link and do not expose a Telegram identifier in the link or message.
- **AC-5 — Mini App compatibility.** The existing authenticated Mini App invite
  endpoint, Settings invite row, Credits invite button, attribution, reward,
  cap, and privacy contracts remain unchanged.

## Edge and error criteria

- **EC-1.** `/invite` is private-chat only. In a group it sends the existing
  localized private-chat guidance and never issues or reveals a referral link.
- **ERR-1.** When the Mini App/referral configuration is disabled or lacks a
  validated bot username, `/invite` returns a localized unavailable message
  and does not issue a code.
- **ERR-2.** Storage failure returns the same generic localized unavailable
  message. Logs contain only the exception type, never a user identifier,
  invite code, database URL, credential, or raw exception text.

## Constraints and out of scope

- No schema migration, new referral economics, subscription gift, unlimited
  plan, Stars transfer, extra invitee reward, dependency, or feature-flag
  change.
- No callback state or persisted pending invitation: the URL button is enough
  to continue into Telegram's native share composer.
- Preserve deterministic learning behavior when AI, Voice, Stars, or Mini App
  features are disabled.

## Verification commands

```bash
.venv/bin/python -m unittest tests.test_telegram_invite_command_v1 -v
.venv/bin/python -m unittest tests.test_referral_program_v1 tests.test_telegram_miniapp_v1 -v
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q bot.py mydictionary tests
git diff --check
```
