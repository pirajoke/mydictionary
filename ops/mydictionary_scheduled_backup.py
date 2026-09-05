#!/usr/bin/env python3
"""Run the verified Lexi backup through the live admin container."""

from __future__ import annotations

import logging
import os
from pathlib import Path
import subprocess


LOGGER = logging.getLogger("mydictionary-scheduled-backup")
DEFAULT_DOCKER_BINARY = "/usr/bin/docker"
CONTAINER = "main-manager-emergency-mydictionary-admin-1"
BACKUP_COMMAND = (
    "exec",
    CONTAINER,
    "env",
    "MYDICTIONARY_APP_ROOT=/app/state",
    "MYDICTIONARY_BACKUP_DIR=/app/state/backups",
    "MYDICTIONARY_PGDUMP_DATABASE=mydictionary",
    "python",
    "/app/ops/mydictionary_backup.py",
)


class ScheduledBackupError(RuntimeError):
    """The scheduled production backup cannot be run safely."""


def _docker_binary() -> str:
    configured = str(
        os.environ.get("MYDICTIONARY_DOCKER_BINARY") or DEFAULT_DOCKER_BINARY
    ).strip()
    path = Path(configured)
    if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
        raise ScheduledBackupError("Docker executable is missing or unsafe")
    return str(path)


def _run(docker: str, *arguments: str, capture: bool = False) -> subprocess.CompletedProcess:
    return subprocess.run(
        [docker, *arguments],
        check=True,
        capture_output=capture,
        text=capture,
        timeout=3600,
    )


def run_scheduled_backup() -> None:
    docker = _docker_binary()
    status = _run(
        docker,
        "inspect",
        "-f",
        "{{.State.Running}}",
        CONTAINER,
        capture=True,
    )
    if status.stdout.strip() != "true":
        raise ScheduledBackupError("Lexi admin container is not running")
    _run(docker, *BACKUP_COMMAND)
    _run(docker, *BACKUP_COMMAND, "--check")


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    try:
        run_scheduled_backup()
        LOGGER.info("Scheduled PostgreSQL backup completed and verified")
        return 0
    except Exception as exc:
        LOGGER.error(
            "Scheduled backup failed: error_type=%s",
            type(exc).__name__,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
