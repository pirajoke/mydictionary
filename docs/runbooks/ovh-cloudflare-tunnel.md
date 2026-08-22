# OVH Cloudflare Tunnel recovery

This runbook restores the public MY DICTIONARY hostname after moving the
application to OVH. It does not authorize access to Cloudflare, enrollment of a
connector, creation or rotation of a tunnel token, DNS changes, or production
service changes. Those remain a separate owner-approved credential action.

## Verified incident shape

The application is healthy when all of these facts hold together:

- `https://mydictionary.meshly.fr/health` returns Cloudflare error `1033`;
- `http://127.0.0.1:8787/health` on OVH returns `200`;
- the bot heartbeat is `ready` on the expected release;
- PostgreSQL is healthy; and
- OVH has no active `cloudflared` process, service, or container.

Cloudflare classifies `1033` as an Argo Tunnel error. In this incident, the
absence of any OVH connector alongside a healthy loopback origin isolates the
disconnected connector as the cause. Do not change the application, database,
or public DNS before proving the connector state.

## Chosen connector contract

Use one remotely-managed tunnel connector on OVH and keep its routing in the
Cloudflare dashboard:

- public hostname: `mydictionary.meshly.fr`;
- origin service: `http://127.0.0.1:8787`;
- connector: a pinned `cloudflared` release that supports `--token-file`;
- runtime: a dedicated unprivileged `cloudflared` system user;
- token path: `/etc/cloudflared/tunnel.token`;
- token permissions: owner `root`, group `cloudflared`, mode `0640`;
- logs: systemd journal at `info`, never `debug` during enrollment.

Cloudflare added `--token-file` for remotely-managed tunnels in version
`2025.4.0`. It keeps the bearer token out of the process arguments, shell
history, compose files, and environment. Pin a reviewed version rather than
using `latest`; the audited workstation version on 2026-08-22 was `2026.7.1`.

Primary references:

- [Cloudflare Tunnel run parameters](https://developers.cloudflare.com/tunnel/advanced/run-parameters/)
- [Cloudflare Tunnel tokens](https://developers.cloudflare.com/tunnel/advanced/tunnel-tokens/)
- [Run Cloudflare Tunnel as a service](https://developers.cloudflare.com/tunnel/advanced/local-management/as-a-service/)

## Owner-gated enrollment

Before touching OVH, the owner must approve this exact scope and provide a
token for the existing remotely-managed tunnel, or create a replacement tunnel
whose public hostname points to the loopback origin above. Treat the token as a
credential: do not paste it into a command, issue, chat, environment variable,
unit file, or deployment log.

Enroll it through a hidden/credential-safe input path into a newly created
regular file. Before starting the connector, verify only metadata:

```text
path=/etc/cloudflared/tunnel.token
owner=root
group=cloudflared
mode=0640
non_empty=true
symlink=false
```

Never print the byte count, fingerprint, token, or installation command copied
from the Cloudflare dashboard.

## Service shape

Install the pinned binary from Cloudflare's official package or release and
verify the reported version before service creation. The systemd service must
use the token file, not `--token`:

```ini
[Unit]
Description=MY DICTIONARY Cloudflare Tunnel connector
Wants=network-online.target
After=network-online.target

[Service]
Type=notify
User=cloudflared
Group=cloudflared
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate --loglevel info run --token-file /etc/cloudflared/tunnel.token
Restart=on-failure
RestartSec=5s
NoNewPrivileges=true
PrivateTmp=true
ProtectHome=true
ProtectSystem=strict
ReadOnlyPaths=/etc/cloudflared/tunnel.token
RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6

[Install]
WantedBy=multi-user.target
```

Do not expose port `8787` in the firewall. The connector originates outbound
connections and reaches the existing loopback listener locally.

## Acceptance checks

Capture values only; never copy connector logs into the receipt.

1. `cloudflared.service` is enabled and active with zero restarts after a
   five-minute observation.
2. Its process arguments contain `--token-file` and do not contain a token.
3. OVH loopback `/health` remains `200`.
4. Public `/health` becomes `200` and returns only the public health contract.
5. Public `/admin/login` becomes `200`; authentication and security headers are
   unchanged.
6. Bot heartbeat remains `ready` on the same release, exactly one bot process
   runs, PostgreSQL stays healthy, and its Alembic revision is unchanged.
7. AI/Voice/Stars flags, payments, user access, and autodeploy are unchanged.
8. Recent connector, bot, and admin logs contain no token pattern, traceback,
   polling conflict, or repeated origin error.

If any check fails, stop and disable only `cloudflared.service`. Do not restart
the bot, migrate or restore the database, rotate credentials, open firewall
ports, or change the Cloudflare route as an improvised rollback.

## Durable receipt

Record the connector version, service enabled/active state, public and loopback
HTTP codes, release SHA, database revision, restart counts, and the unchanged
feature flags. Store neither tunnel identifiers nor credentials. Update roadmap
issue #6 only after the public checks have remained healthy for five minutes.
