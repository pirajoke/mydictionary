#!/usr/bin/env python3
"""Upload only an age-encrypted, verified MY DICTIONARY backup off-site."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import logging
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Callable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ops import mydictionary_backup as backup


LOGGER = logging.getLogger("mydictionary-offsite-backup")
AGE_RECIPIENT_RE = re.compile(r"^age1[0-9a-z]{50,100}$")
REMOTE_RE = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}:[A-Za-z0-9_./-]{1,512}$"
)
SAFE_ENVIRONMENT_NAMES = ("HOME", "PATH", "LANG", "LC_ALL", "TMPDIR")


class OffsiteBackupError(RuntimeError):
    """The encrypted backup contract is incomplete or unsafe."""


@dataclass(frozen=True)
class Config:
    age_binary: str
    rclone_binary: str
    age_recipient: str
    remote_prefix: str
    timeout_seconds: int

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> "Config":
        env = values if values is not None else os.environ
        recipient = str(env.get("MYDICTIONARY_BACKUP_AGE_RECIPIENT") or "").strip()
        remote = str(env.get("MYDICTIONARY_BACKUP_RCLONE_REMOTE") or "").strip()
        if not AGE_RECIPIENT_RE.fullmatch(recipient):
            raise OffsiteBackupError(
                "MYDICTIONARY_BACKUP_AGE_RECIPIENT must be a public age recipient"
            )
        if (
            not REMOTE_RE.fullmatch(remote)
            or ".." in remote.split(":", 1)[1].split("/")
            or remote.endswith("/")
        ):
            raise OffsiteBackupError(
                "MYDICTIONARY_BACKUP_RCLONE_REMOTE must be a safe remote:path prefix"
            )
        try:
            timeout = int(env.get("MYDICTIONARY_OFFSITE_TIMEOUT_SECONDS", "1800"))
        except ValueError as exc:
            raise OffsiteBackupError(
                "MYDICTIONARY_OFFSITE_TIMEOUT_SECONDS must be an integer"
            ) from exc
        if not 30 <= timeout <= 7200:
            raise OffsiteBackupError(
                "MYDICTIONARY_OFFSITE_TIMEOUT_SECONDS is outside the allowed range"
            )
        return cls(
            age_binary=_binary(env, "MYDICTIONARY_AGE", "age"),
            rclone_binary=_binary(env, "MYDICTIONARY_RCLONE", "rclone"),
            age_recipient=recipient,
            remote_prefix=remote,
            timeout_seconds=timeout,
        )


@dataclass(frozen=True)
class UploadResult:
    source_name: str
    encrypted_name: str
    remote_object: str
    encrypted_sha256: str | None
    executed: bool


def _binary(values: Mapping[str, str], name: str, default: str) -> str:
    value = str(values.get(name) or default).strip()
    if not value or len(value) > 4096 or any(ord(char) < 32 for char in value):
        raise OffsiteBackupError(f"Invalid executable setting: {name}")
    return value


def _environment() -> dict[str, str]:
    return {
        name: os.environ[name]
        for name in SAFE_ENVIRONMENT_NAMES
        if os.environ.get(name)
    }


def run(command: list[str], *, timeout: int) -> subprocess.CompletedProcess:
    LOGGER.info("Running off-site backup command: %s", Path(command[0]).name)
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=_environment(),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def upload_latest(
    backup_config: backup.Config,
    config: Config,
    *,
    execute: bool,
    runner: Callable[..., subprocess.CompletedProcess] = run,
) -> UploadResult:
    record = backup.verify_latest(backup_config)
    encrypted_name = f"{record.path.name}.age"
    remote_object = f"{config.remote_prefix}/{encrypted_name}"
    if not execute:
        return UploadResult(
            record.path.name,
            encrypted_name,
            remote_object,
            None,
            False,
        )
    with tempfile.TemporaryDirectory(prefix="mydictionary-offsite-") as directory:
        temporary = Path(directory)
        os.chmod(temporary, 0o700)
        encrypted = temporary / encrypted_name
        runner(
            [
                config.age_binary,
                "--recipient",
                config.age_recipient,
                "--output",
                str(encrypted),
                str(record.path),
            ],
            timeout=config.timeout_seconds,
        )
        if not encrypted.is_file() or encrypted.stat().st_size <= 0:
            raise OffsiteBackupError("age did not create an encrypted backup")
        os.chmod(encrypted, 0o600)
        digest = _sha256(encrypted)
        checksum = temporary / f"{encrypted_name}.sha256"
        checksum.write_text(f"{digest}  {encrypted_name}\n", encoding="ascii")
        os.chmod(checksum, 0o600)
        runner(
            [
                config.rclone_binary,
                "copyto",
                "--immutable",
                str(encrypted),
                remote_object,
            ],
            timeout=config.timeout_seconds,
        )
        runner(
            [
                config.rclone_binary,
                "copyto",
                "--immutable",
                str(checksum),
                f"{remote_object}.sha256",
            ],
            timeout=config.timeout_seconds,
        )
    return UploadResult(
        record.path.name,
        encrypted_name,
        remote_object,
        digest,
        True,
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--execute", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    result = upload_latest(
        backup.Config.from_env(),
        Config.from_env(),
        execute=args.execute,
    )
    print(f"mode={'execute' if result.executed else 'preview'}")
    print(f"source={result.source_name}")
    print(f"remote={result.remote_object}")
    if result.encrypted_sha256:
        print(f"encrypted_sha256={result.encrypted_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
