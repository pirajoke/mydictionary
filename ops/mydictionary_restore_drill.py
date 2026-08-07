#!/usr/bin/env python3
"""Verify an encrypted off-site backup through an isolated PostgreSQL restore."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import tempfile
from typing import Callable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ops import mydictionary_backup as backup
from ops import mydictionary_offsite_backup as offsite


LOGGER = logging.getLogger("mydictionary-restore-drill")
ENCRYPTED_BACKUP_NAME_RE = re.compile(
    r"^(mydictionary-[0-9]{8}T[0-9]{6}\.[0-9]{6}Z-"
    r"[0-9a-f]{12}\.dump)\.age$"
)
DRILL_DATABASE_RE = re.compile(
    r"^mydictionary_restore_drill_[0-9]{8}t[0-9]{6}z_[0-9a-f]{8}$"
)
CHECKSUM_RE = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9_.-]+)\n$")
RECEIPT_SCHEMA_VERSION = 1


class RestoreDrillError(RuntimeError):
    """The encrypted restore drill is incomplete, unsafe, or failed."""


@dataclass(frozen=True)
class Config:
    age_binary: str
    rclone_binary: str
    pg_restore_binary: str
    psql_binary: str
    createdb_binary: str
    dropdb_binary: str
    age_identity: Path
    remote_prefix: str
    expected_revision: str
    receipt_dir: Path
    timeout_seconds: int

    @classmethod
    def from_env(cls, values: Mapping[str, str] | None = None) -> "Config":
        env = values if values is not None else os.environ
        remote = _required(env, "MYDICTIONARY_BACKUP_RCLONE_REMOTE")
        if (
            not offsite.REMOTE_RE.fullmatch(remote)
            or ".." in remote.split(":", 1)[1].split("/")
            or remote.endswith("/")
        ):
            raise RestoreDrillError(
                "MYDICTIONARY_BACKUP_RCLONE_REMOTE must be a safe remote:path prefix"
            )
        identity = _absolute_path(
            env, "MYDICTIONARY_BACKUP_AGE_IDENTITY", require_file=True
        )
        _require_private_file(identity, "age identity")
        revision = _required(env, "MYDICTIONARY_RESTORE_EXPECTED_REVISION")
        if not backup.REVISION_RE.fullmatch(revision):
            raise RestoreDrillError(
                "MYDICTIONARY_RESTORE_EXPECTED_REVISION is invalid"
            )
        receipt_dir = _absolute_path(
            env, "MYDICTIONARY_RESTORE_DRILL_RECEIPT_DIR", require_file=False
        )
        if receipt_dir.exists():
            _require_private_directory(receipt_dir, "restore receipt directory")
        elif not receipt_dir.parent.is_dir():
            raise RestoreDrillError(
                "Restore receipt directory parent must already exist"
            )
        try:
            timeout = int(env.get("MYDICTIONARY_RESTORE_TIMEOUT_SECONDS", "1800"))
        except ValueError as exc:
            raise RestoreDrillError(
                "MYDICTIONARY_RESTORE_TIMEOUT_SECONDS must be an integer"
            ) from exc
        if not 30 <= timeout <= 7200:
            raise RestoreDrillError(
                "MYDICTIONARY_RESTORE_TIMEOUT_SECONDS is outside the allowed range"
            )
        return cls(
            age_binary=offsite._binary(env, "MYDICTIONARY_AGE", "age"),
            rclone_binary=offsite._binary(env, "MYDICTIONARY_RCLONE", "rclone"),
            pg_restore_binary=offsite._binary(
                env, "MYDICTIONARY_PG_RESTORE", "pg_restore"
            ),
            psql_binary=offsite._binary(env, "MYDICTIONARY_PSQL", "psql"),
            createdb_binary=offsite._binary(
                env, "MYDICTIONARY_CREATEDB", "createdb"
            ),
            dropdb_binary=offsite._binary(env, "MYDICTIONARY_DROPDB", "dropdb"),
            age_identity=identity,
            remote_prefix=remote,
            expected_revision=revision,
            receipt_dir=receipt_dir,
            timeout_seconds=timeout,
        )


@dataclass(frozen=True)
class RestoreDrillResult:
    encrypted_name: str
    remote_object: str
    restored_revision: str | None
    encrypted_sha256: str | None
    receipt_path: Path | None
    executed: bool


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _required(values: Mapping[str, str], name: str) -> str:
    value = str(values.get(name) or "").strip()
    if not value:
        raise RestoreDrillError(f"{name} is required")
    return value


def _absolute_path(
    values: Mapping[str, str], name: str, *, require_file: bool
) -> Path:
    raw = Path(_required(values, name)).expanduser()
    if not raw.is_absolute():
        raise RestoreDrillError(f"{name} must be an absolute path")
    if raw.is_symlink():
        raise RestoreDrillError(f"{name} cannot be a symlink")
    resolved = raw.resolve()
    if require_file and not resolved.is_file():
        raise RestoreDrillError(f"{name} must identify a regular file")
    return resolved


def _require_private_file(path: Path, label: str) -> None:
    try:
        unsafe = path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077
    except OSError as exc:
        raise RestoreDrillError(f"{label} is missing or unsafe") from exc
    if unsafe:
        raise RestoreDrillError(f"{label} is missing or unsafe")
    if hasattr(os, "getuid") and path.stat().st_uid != os.getuid():
        raise RestoreDrillError(f"{label} must be owned by the current user")


def _require_private_directory(path: Path, label: str) -> None:
    try:
        unsafe = path.is_symlink() or not path.is_dir() or path.stat().st_mode & 0o077
    except OSError as exc:
        raise RestoreDrillError(f"{label} is missing or unsafe") from exc
    if unsafe:
        raise RestoreDrillError(f"{label} is missing or unsafe")
    if hasattr(os, "getuid") and path.stat().st_uid != os.getuid():
        raise RestoreDrillError(f"{label} must be owned by the current user")


def _environment(*, database_name: str | None = None) -> dict[str, str]:
    names = backup.SAFE_ENVIRONMENT_NAMES + backup.LIBPQ_ENVIRONMENT_NAMES
    result = {name: os.environ[name] for name in names if os.environ.get(name)}
    if database_name is not None:
        result["PGDATABASE"] = database_name
    return result


def run(
    command: list[str], *, env: Mapping[str, str], timeout: int
) -> subprocess.CompletedProcess:
    LOGGER.info("Running restore drill command: %s", Path(command[0]).name)
    return subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
        env=dict(env),
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_encrypted_name(value: str) -> str:
    name = str(value or "").strip()
    if not ENCRYPTED_BACKUP_NAME_RE.fullmatch(name) or Path(name).name != name:
        raise RestoreDrillError("Encrypted backup name is invalid")
    return name


def _parse_checksum(path: Path, encrypted_name: str) -> str:
    try:
        content = path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as exc:
        raise RestoreDrillError("Encrypted checksum is unreadable") from exc
    match = CHECKSUM_RE.fullmatch(content)
    if not match or match.group(2) != encrypted_name:
        raise RestoreDrillError("Encrypted checksum record is invalid")
    return match.group(1)


def _drill_database_name(
    observed_at: datetime, token_factory: Callable[[int], str]
) -> str:
    timestamp = observed_at.astimezone(timezone.utc).strftime("%Y%m%dt%H%M%Sz")
    name = f"mydictionary_restore_drill_{timestamp}_{token_factory(4)}"
    if not DRILL_DATABASE_RE.fullmatch(name):
        raise RestoreDrillError("Generated restore database name is unsafe")
    return name


def _write_receipt(
    config: Config,
    *,
    encrypted_name: str,
    encrypted_sha256: str,
    restored_revision: str,
    completed_at: datetime,
) -> Path:
    if config.receipt_dir.exists():
        _require_private_directory(config.receipt_dir, "restore receipt directory")
    else:
        config.receipt_dir.mkdir(mode=0o700)
        _require_private_directory(config.receipt_dir, "restore receipt directory")
    timestamp = completed_at.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    path = config.receipt_dir / (
        f"mydictionary-restore-drill-{timestamp}-{encrypted_sha256[:12]}.json"
    )
    if path.exists() or path.is_symlink():
        raise RestoreDrillError("Restore receipt destination already exists")
    payload = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "encrypted_backup": encrypted_name,
        "encrypted_sha256": encrypted_sha256,
        "database_revision": restored_revision,
        "completed_at": completed_at.astimezone(timezone.utc).isoformat(),
    }
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=config.receipt_dir
    )
    temporary = Path(temporary_name)
    try:
        os.chmod(temporary, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=True, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        return path
    finally:
        temporary.unlink(missing_ok=True)


def restore_drill(
    config: Config,
    encrypted_name: str,
    *,
    execute: bool,
    runner: Callable[..., subprocess.CompletedProcess] = run,
    now: Callable[[], datetime] = utcnow,
    token_factory: Callable[[int], str] = secrets.token_hex,
) -> RestoreDrillResult:
    name = _validate_encrypted_name(encrypted_name)
    remote_object = f"{config.remote_prefix}/{name}"
    if not execute:
        return RestoreDrillResult(name, remote_object, None, None, None, False)

    observed_at = now().astimezone(timezone.utc)
    database_name = _drill_database_name(observed_at, token_factory)
    database_created = False
    restored_revision: str | None = None
    encrypted_digest: str | None = None
    receipt: Path | None = None
    environment = _environment()

    with tempfile.TemporaryDirectory(prefix="mydictionary-restore-drill-") as raw:
        temporary = Path(raw)
        os.chmod(temporary, 0o700)
        encrypted = temporary / name
        checksum = temporary / f"{name}.sha256"
        name_match = ENCRYPTED_BACKUP_NAME_RE.fullmatch(name)
        if name_match is None:  # guarded by _validate_encrypted_name
            raise RestoreDrillError("Encrypted backup name is invalid")
        decrypted = temporary / name_match.group(1)
        runner(
            [config.rclone_binary, "copyto", remote_object, str(encrypted)],
            env=environment,
            timeout=config.timeout_seconds,
        )
        runner(
            [
                config.rclone_binary,
                "copyto",
                f"{remote_object}.sha256",
                str(checksum),
            ],
            env=environment,
            timeout=config.timeout_seconds,
        )
        for path, label in (
            (encrypted, "encrypted backup"),
            (checksum, "encrypted checksum"),
        ):
            if not path.is_file() or path.is_symlink() or path.stat().st_size <= 0:
                raise RestoreDrillError(f"Downloaded {label} is missing or unsafe")
            os.chmod(path, 0o600)
        encrypted_digest = _sha256(encrypted)
        if _parse_checksum(checksum, name) != encrypted_digest:
            raise RestoreDrillError("Encrypted backup checksum does not match")
        runner(
            [
                config.age_binary,
                "--decrypt",
                "--identity",
                str(config.age_identity),
                "--output",
                str(decrypted),
                str(encrypted),
            ],
            env=environment,
            timeout=config.timeout_seconds,
        )
        if (
            not decrypted.is_file()
            or decrypted.is_symlink()
            or decrypted.stat().st_size <= 0
        ):
            raise RestoreDrillError("age did not create a decrypted PostgreSQL dump")
        os.chmod(decrypted, 0o600)
        runner(
            [config.pg_restore_binary, "--list", str(decrypted)],
            env=environment,
            timeout=config.timeout_seconds,
        )
        try:
            runner(
                [
                    config.createdb_binary,
                    "--maintenance-db=postgres",
                    "--template=template0",
                    "--encoding=UTF8",
                    database_name,
                ],
                env=environment,
                timeout=config.timeout_seconds,
            )
            database_created = True
            runner(
                [
                    config.pg_restore_binary,
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    "--dbname",
                    database_name,
                    str(decrypted),
                ],
                env=environment,
                timeout=config.timeout_seconds,
            )
            revision_result = runner(
                [
                    config.psql_binary,
                    "--dbname",
                    database_name,
                    "--no-psqlrc",
                    "--tuples-only",
                    "--no-align",
                    "--command",
                    "SELECT version_num FROM alembic_version;",
                ],
                env=environment,
                timeout=config.timeout_seconds,
            )
            revisions = [
                line.strip()
                for line in str(revision_result.stdout or "").splitlines()
                if line.strip()
            ]
            if revisions != [config.expected_revision]:
                raise RestoreDrillError(
                    "Restored database revision does not match the expected revision"
                )
            restored_revision = revisions[0]
        finally:
            if database_created:
                runner(
                    [
                        config.dropdb_binary,
                        "--maintenance-db=postgres",
                        "--force",
                        database_name,
                    ],
                    env=environment,
                    timeout=config.timeout_seconds,
                )

    receipt = _write_receipt(
        config,
        encrypted_name=name,
        encrypted_sha256=encrypted_digest,
        restored_revision=restored_revision,
        completed_at=observed_at,
    )
    return RestoreDrillResult(
        name,
        remote_object,
        restored_revision,
        encrypted_digest,
        receipt,
        True,
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--encrypted-name", required=True)
    result.add_argument("--execute", action="store_true")
    result.add_argument(
        "--confirm-isolated-database",
        action="store_true",
        help="confirm creation and deletion of a generated restore-drill database",
    )
    return result


def main() -> int:
    args = parser().parse_args()
    if args.execute and not args.confirm_isolated_database:
        raise RestoreDrillError(
            "--execute requires --confirm-isolated-database"
        )
    result = restore_drill(
        Config.from_env(), args.encrypted_name, execute=args.execute
    )
    print(f"mode={'execute' if result.executed else 'preview'}")
    print(f"encrypted_backup={result.encrypted_name}")
    print(f"remote={result.remote_object}")
    if result.restored_revision:
        print(f"database_revision={result.restored_revision}")
    if result.encrypted_sha256:
        print(f"encrypted_sha256={result.encrypted_sha256}")
    if result.receipt_path:
        print(f"receipt={result.receipt_path}")
    return 0


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    raise SystemExit(main())
