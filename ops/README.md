# Local automatic deployment

The production bot is deployed by a local macOS LaunchAgent. The deployer polls
`origin/main`; pull-request branches never execute on the production host.

For each new revision the deployer:

1. fetches the exact `origin/main` commit;
2. extracts it into a new immutable release directory;
3. creates a release-specific Python virtual environment;
4. installs dependencies and runs the deterministic test suite;
5. atomically switches the `current` symlink;
6. restarts the bot and verifies that launchd reports it as running;
7. restores the previous release if the health check fails.

Mutable dictionaries, learning progress, configuration, and audio cache stay in
the external data directory. A commit that changes a mutable dictionary is
rejected and requires an explicit data migration. Rewritten or non-fast-forward
`main` history is also rejected.

Required environment variables:

- `MYDICTIONARY_APP_ROOT`
- `MYDICTIONARY_REPOSITORY_URL`
- `MYDICTIONARY_BOOTSTRAP_PYTHON`

Optional environment variables:

- `MYDICTIONARY_SERVICE_LABEL` (defaults to the existing bot service label)

The production LaunchAgent configuration is local-only because it contains
host paths. It must not be committed to this public repository.
