# Completion Ops Contract

## Scope

Prepare MY DICTIONARY for a later Telegram token rotation, isolated Telegram
Stars test run, and encrypted off-site backup without contacting Telegram,
uploading data, deleting logs, changing production, or enabling providers.

## Acceptance criteria

- AC-1: The bot can load `BOT_TOKEN` from an absolute owner-only regular file
  named by `BOT_TOKEN_FILE` when `BOT_TOKEN` is absent.
- AC-2: Test Stars preflight can load a dedicated token and one positive test
  user ID from an absolute owner-only JSON credential file without returning
  either value in its safe result.
- AC-3: A log-security preview reports only occurrence counts and byte size;
  execution writes a new mode-`0600` sanitized copy and leaves the source
  unchanged.
- AC-4: Off-site backup `--check` verifies local `age` and `rclone` binaries and
  the configured rclone remote name without uploading or reading backup data.

## Edge criteria

- EC-1: One optional trailing newline is accepted in a plain token file.
- EC-2: Credential files and outputs reject symlinks, non-regular files,
  relative paths, and group/world permissions.
- EC-3: Credential-file values may not coexist with inline token or test-user
  values, preventing accidental production/test mixing.
- EC-4: Sanitization recognizes bare Telegram bot tokens and Bot API URL tokens
  while preserving all unrelated bytes.

## Failure criteria

- ERR-1: Invalid token formats and non-positive/non-integer test user IDs fail
  closed without creating output.
- ERR-2: Existing sanitizer destinations are never overwritten.
- ERR-3: Off-site preflight fails if either binary is missing or the configured
  rclone remote is absent.

## Out of scope

- No BotFather action, token rotation, production plist edit, service restart,
  log deletion, Telegram API call, Stars transaction, AI call, upload, restore,
  merge, or production deployment.
