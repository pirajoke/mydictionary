#!/usr/bin/env python3
"""Create and verify private PostgreSQL backups for MY DICTIONARY."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Any, Callable, Iterator, MutableMapping

from sqlalchemy.engine import make_url
from sqlalchemy.exc import ArgumentError


LOGGER = logging.getLogger("mydictionary-backup")
STATE_SCHEMA_VERSION = 1
BACKUP_NAME_RE = re.compile(
    r"^mydictionary-[0-9]{8}T[0-9]{6}\.[0-9]{6}Z-[0-9a-f]{12}\.dump$"
)
REVISION_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
DATABASE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,63}$")
SAFE_ENVIRONMENT_NAMES = (
    "HOME",
    "PATH",
    "LANG",
    "LC_ALL",
    "TMPDIR",
)
LIBPQ_ENVIRONMENT_NAMES = (
    "PGHOST",
    "PGPORT",
    "PGUSER",
    "PGPASSFILE",
    "PGSSLMODE",
    "PGSERVICE",
    "PGSERVICEFILE",
)
DATABASE_URL_DRIVERS = frozenset(
    {"postgres", "postgresql", "postgresql+psycopg"}
)
DERIVED_LIBPQ_ENVIRONMENT_NAMES = (
    "PGHOST",
    "PGPORT",
    "PGUSER",
    "PGSSLMODE",
)


class BackupError(RuntimeError):
    """Backup policy or integrity validation failed."""


@dataclass(frozen=True)
class Config:
    app_root: Path
    backup_dir: Path
    database_target: str
    pg_dump_binary: str
    pg_restore_binary: str
    psql_binary: str
    retention_days: int
    minimum_backups: int
    maximum_age_seconds: int
    minimum_free_bytes: int
    command_timeout_seconds: int
    lock_file: Path
    state_file: Path

    @classmethod
    def from_env(cls, values: dict[str, str] | None = None) -> "Config":
        env = values if values is not None else os.environ
        app_root = Path(_required(env, "MYDICTIONARY_APP_ROOT")).expanduser().resolve()
        database_target = _required(env, "MYDICTIONARY_PGDUMP_DATABASE")
        if not DATABASE_NAME_RE.fullmatch(database_target):
            raise BackupError(
                "MYDICTIONARY_PGDUMP_DATABASE must be a plain database name; "
                "use PGHOST, PGPORT, and PGUSER for connection settings"
            )
        return cls(
            app_root=app_root,
            backup_dir=Path(
                env.get("MYDICTIONARY_BACKUP_DIR", "").strip()
                or app_root / "backups"
            ).expanduser().resolve(),
            database_target=database_target,
            pg_dump_binary=_binary(env, "MYDICTIONARY_PG_DUMP", "pg_dump"),
            pg_restore_binary=_binary(
                env, "MYDICTIONARY_PG_RESTORE", "pg_restore"
            ),
            psql_binary=_binary(env, "MYDICTIONARY_PSQL", "psql"),
            retention_days=_bounded_int(
                env,
                "MYDICTIONARY_BACKUP_RETENTION_DAYS",
                default=30,
                minimum=7,
                maximum=3650,
            ),
            minimum_backups=_bounded_int(
                env,
                "MYDICTIONARY_BACKUP_MINIMUM_COUNT",
                default=7,
                minimum=2,
                maximum=365,
            ),
            maximum_age_seconds=_bounded_int(
                env,
                "MYDICTIONARY_BACKUP_MAX_AGE_SECONDS",
                default=93600,
                minimum=3600,
                maximum=604800,
            ),
            minimum_free_bytes=_bounded_int(
                env,
                "MYDICTIONARY_BACKUP_MIN_FREE_BYTES",
                default=1073741824,
                minimum=104857600,
                maximum=1099511627776,
            ),
            command_timeout_seconds=_bounded_int(
                env,
                "MYDICTIONARY_BACKUP_COMMAND_TIMEOUT_SECONDS",
                default=1800,
                minimum=30,
                maximum=7200,
            ),
            lock_file=app_root / ".backup.lock",
            state_file=app_root / ".backup-state.json",
        )


@dataclass(frozen=True)
class BackupRecord:
    path: Path
    digest_sha256: str
    size_bytes: int
    database_revision: str
    created_at: datetime

    def payload(self) -> dict[str, Any]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "backup_file": self.path.name,
            "sha256": self.digest_sha256,
            "size_bytes": self.size_bytes,
            "database_revision": self.database_revision,
            "created_at": self.created_at.isoformat(),
        }


def _required(values: dict[str, str] | os._Environ[str], name: str) -> str:
    value = str(values.get(name) or "").strip()
    if not value:
        raise BackupError(f"Missing required setting: {name}")
    return value


def _binary(
    values: dict[str, str] | os._Environ[str], name: str, default: str
) -> str:
    value = str(values.get(name) or default).strip()
    if (
        not value
        or len(value) > 4096
        or any(
            ord(character) < 32 or ord(character) == 127
            for character in value
        )
    ):
        raise BackupError(f"Invalid executable setting: {name}")
    return value


def _bounded_int(
    values: dict[str, str] | os._Environ[str],
    name: str,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(values.get(name, str(default)))
    except ValueError as exc:
        raise BackupError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise BackupError(f"{name} is outside the allowed range")
    return value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _selected_environment(names: tuple[str, ...]) -> dict[str, str]:
    return {name: os.environ[name] for name in names if os.environ.get(name)}


def _database_environment(config: Config) -> dict[str, str]:
    environment = _selected_environment(
        SAFE_ENVIRONMENT_NAMES + LIBPQ_ENVIRONMENT_NAMES
    )
    environment["PGDATABASE"] = config.database_target
    return environment


def _pgpass_escape(value: str) -> str:
    if any(character in value for character in ("\x00", "\r", "\n")):
        raise BackupError("DATABASE_URL contains an unsafe libpq value")
    return value.replace("\\", "\\\\").replace(":", "\\:")


@contextmanager
def _database_url_libpq_environment(
    config: Config,
    values: MutableMapping[str, str] | None = None,
) -> Iterator[None]:
    environment = values if values is not None else os.environ
    raw_url = str(environment.get("DATABASE_URL") or "").strip()
    if not raw_url:
        yield
        return
    try:
        database_url = make_url(raw_url)
    except ArgumentError as exc:
        raise BackupError("DATABASE_URL is not a valid PostgreSQL URL") from exc
    if database_url.drivername not in DATABASE_URL_DRIVERS:
        raise BackupError("DATABASE_URL must use PostgreSQL")
    database = str(database_url.database or "")
    unsupported_query = set(database_url.query) - {"host", "sslmode"}
    if unsupported_query:
        raise BackupError("DATABASE_URL contains unsupported connection parameters")
    query_host = database_url.query.get("host")
    if query_host is not None and not isinstance(query_host, str):
        raise BackupError("DATABASE_URL contains an invalid PostgreSQL host")
    if database_url.host and query_host is not None:
        raise BackupError("DATABASE_URL contains conflicting PostgreSQL hosts")
    host = str(
        database_url.host
        or query_host
        or environment.get("PGHOST")
        or ""
    ).strip()
    username = str(
        database_url.username or environment.get("PGUSER") or ""
    ).strip()
    if database != config.database_target:
        raise BackupError("DATABASE_URL database does not match backup target")
    if not host or not username:
        raise BackupError("DATABASE_URL must include PostgreSQL host and user")
    try:
        port = str(database_url.port or environment.get("PGPORT") or 5432)
    except ValueError as exc:
        raise BackupError("DATABASE_URL contains an invalid PostgreSQL port") from exc
    derived = {
        "PGHOST": host,
        "PGPORT": port,
        "PGUSER": username,
    }
    sslmode = database_url.query.get("sslmode")
    if sslmode is not None:
        if not isinstance(sslmode, str) or not sslmode.strip():
            raise BackupError("DATABASE_URL contains an invalid sslmode")
        derived["PGSSLMODE"] = sslmode.strip()
    for name, expected in derived.items():
        configured = str(environment.get(name) or "").strip()
        if configured and configured != expected:
            raise BackupError(f"{name} conflicts with DATABASE_URL")
    configured_database = str(environment.get("PGDATABASE") or "").strip()
    if configured_database and configured_database != config.database_target:
        raise BackupError("PGDATABASE conflicts with backup target")
    if environment.get("PGSERVICE") or environment.get("PGSERVICEFILE"):
        raise BackupError("DATABASE_URL cannot be combined with a libpq service")
    if database_url.password is not None and environment.get("PGPASSFILE"):
        raise BackupError("DATABASE_URL password cannot be combined with PGPASSFILE")

    original = {
        name: environment.get(name)
        for name in DERIVED_LIBPQ_ENVIRONMENT_NAMES + ("PGPASSFILE",)
    }
    temporary_pgpass: Path | None = None
    try:
        environment.update(derived)
        password = database_url.password
        if password is not None and not environment.get("PGPASSFILE"):
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                prefix=".mydictionary-pgpass-",
                delete=False,
            ) as handle:
                temporary_pgpass = Path(handle.name)
                os.chmod(temporary_pgpass, 0o600)
                handle.write(
                    ":".join(
                        _pgpass_escape(value)
                        for value in (
                            host,
                            port,
                            config.database_target,
                            username,
                            str(password),
                        )
                    )
                    + "\n"
                )
                handle.flush()
                os.fsync(handle.fileno())
            environment["PGPASSFILE"] = str(temporary_pgpass)
        yield
    finally:
        if temporary_pgpass is not None:
            temporary_pgpass.unlink(missing_ok=True)
        for name, previous in original.items():
            if previous is None:
                environment.pop(name, None)
            else:
                environment[name] = previous


def run(
    command: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout: int = 1800,
) -> subprocess.CompletedProcess:
    LOGGER.info("Running backup command: %s", Path(command[0]).name)
    environment = env if env is not None else _selected_environment(
        SAFE_ENVIRONMENT_NAMES
    )
    return subprocess.run(
        command,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            os.chmod(temporary, 0o600)
            json.dump(
                payload,
                handle,
                ensure_ascii=True,
                sort_keys=True,
                separators=(",", ":"),
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BackupError(f"Invalid backup metadata: {path.name}") from exc
    if not isinstance(value, dict):
        raise BackupError(f"Invalid backup metadata: {path.name}")
    return value


def _prepare_destination(
    config: Config, *, create: bool, require_free_space: bool = False
) -> None:
    if not config.app_root.is_dir():
        raise BackupError("Application root does not exist")
    if create:
        config.backup_dir.mkdir(parents=True, exist_ok=True)
        os.chmod(config.backup_dir, 0o700)
    if not config.backup_dir.is_dir():
        raise BackupError("Backup destination does not exist")
    if config.backup_dir.stat().st_mode & 0o077:
        raise BackupError("Backup destination is group or world accessible")
    if (
        require_free_space
        and shutil.disk_usage(config.backup_dir).free < config.minimum_free_bytes
    ):
        raise BackupError("Backup destination has insufficient free space")


def _database_revision(config: Config) -> str:
    result = run(
        [
            config.psql_binary,
            "--no-psqlrc",
            "--tuples-only",
            "--no-align",
            "--set=ON_ERROR_STOP=1",
            "--command",
            "select version_num from alembic_version",
        ],
        env=_database_environment(config),
        timeout=config.command_timeout_seconds,
    )
    values = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if len(values) != 1 or not REVISION_RE.fullmatch(values[0]):
        raise BackupError("Database has an invalid migration revision")
    return values[0]


def _manifest_path(backup_path: Path) -> Path:
    return backup_path.with_name(f"{backup_path.name}.json")


def create_backup(
    config: Config, *, now: Callable[[], datetime] = utcnow
) -> BackupRecord:
    _prepare_destination(config, create=True, require_free_space=True)
    observed_at = now().astimezone(timezone.utc)
    revision = _database_revision(config)
    timestamp = observed_at.strftime("%Y%m%dT%H%M%S.%fZ")
    identity = hashlib.sha256(
        f"{timestamp}:{revision}".encode("utf-8")
    ).hexdigest()[:12]
    final_path = config.backup_dir / f"mydictionary-{timestamp}-{identity}.dump"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=config.backup_dir,
            prefix=f".{final_path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        os.chmod(temporary, 0o600)
        environment = _database_environment(config)
        run(
            [
                config.pg_dump_binary,
                "--format=custom",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(temporary),
            ],
            env=environment,
            timeout=config.command_timeout_seconds,
        )
        run(
            [config.pg_restore_binary, "--list", str(temporary)],
            env=_selected_environment(SAFE_ENVIRONMENT_NAMES),
            timeout=config.command_timeout_seconds,
        )
        size_bytes = temporary.stat().st_size
        if size_bytes <= 0:
            raise BackupError("PostgreSQL backup is empty")
        record = BackupRecord(
            path=final_path,
            digest_sha256=_sha256_file(temporary),
            size_bytes=size_bytes,
            database_revision=revision,
            created_at=observed_at,
        )
        if final_path.exists() or _manifest_path(final_path).exists():
            raise BackupError("Backup destination already exists")
        os.replace(temporary, final_path)
        temporary = None
        payload = record.payload()
        try:
            _atomic_write_json(_manifest_path(final_path), payload)
            _atomic_write_json(config.state_file, payload)
        except Exception:
            _manifest_path(final_path).unlink(missing_ok=True)
            final_path.unlink(missing_ok=True)
            raise
        LOGGER.info("PostgreSQL backup completed and verified")
        return record
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _record_from_payload(config: Config, payload: dict[str, Any]) -> BackupRecord:
    if payload.get("schema_version") != STATE_SCHEMA_VERSION:
        raise BackupError("Unsupported backup metadata schema")
    filename = str(payload.get("backup_file") or "")
    if not BACKUP_NAME_RE.fullmatch(filename) or Path(filename).name != filename:
        raise BackupError("Invalid backup filename")
    path = config.backup_dir / filename
    try:
        created_at = datetime.fromisoformat(str(payload["created_at"]))
        if created_at.tzinfo is None:
            raise ValueError
        size_bytes = int(payload["size_bytes"])
    except (KeyError, TypeError, ValueError) as exc:
        raise BackupError("Invalid backup metadata values") from exc
    digest = str(payload.get("sha256") or "")
    revision = str(payload.get("database_revision") or "")
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise BackupError("Invalid backup checksum")
    if size_bytes <= 0 or not REVISION_RE.fullmatch(revision):
        raise BackupError("Invalid backup metadata values")
    return BackupRecord(path, digest, size_bytes, revision, created_at)


def verify_record(
    config: Config,
    record: BackupRecord,
    *,
    now: Callable[[], datetime] = utcnow,
    enforce_age: bool = True,
) -> BackupRecord:
    if not record.path.is_file() or record.path.is_symlink():
        raise BackupError("Backup file is missing or unsafe")
    if record.path.stat().st_mode & 0o077:
        raise BackupError("Backup file is group or world accessible")
    if record.path.stat().st_size != record.size_bytes:
        raise BackupError("Backup size does not match metadata")
    if _sha256_file(record.path) != record.digest_sha256:
        raise BackupError("Backup checksum does not match metadata")
    manifest_path = _manifest_path(record.path)
    try:
        unsafe_manifest = (
            manifest_path.is_symlink() or manifest_path.stat().st_mode & 0o077
        )
    except OSError as exc:
        raise BackupError("Backup manifest is missing or unsafe") from exc
    if unsafe_manifest:
        raise BackupError("Backup manifest is missing or unsafe")
    manifest = _read_json(manifest_path)
    if _record_from_payload(config, manifest) != record:
        raise BackupError("Backup manifest does not match state")
    if enforce_age:
        age = (
            now().astimezone(timezone.utc)
            - record.created_at.astimezone(timezone.utc)
        ).total_seconds()
        if age < -5 or age > config.maximum_age_seconds:
            raise BackupError("Latest verified backup is stale")
    run(
        [config.pg_restore_binary, "--list", str(record.path)],
        env=_selected_environment(SAFE_ENVIRONMENT_NAMES),
        timeout=config.command_timeout_seconds,
    )
    return record


def _read_latest_record(config: Config) -> BackupRecord:
    try:
        unsafe_state = (
            config.state_file.is_symlink()
            or config.state_file.stat().st_mode & 0o077
        )
    except OSError as exc:
        raise BackupError("Backup state is missing or unsafe") from exc
    if unsafe_state:
        raise BackupError("Backup state is missing or unsafe")
    return _record_from_payload(config, _read_json(config.state_file))


def verify_latest(config: Config) -> BackupRecord:
    _prepare_destination(config, create=False)
    record = _read_latest_record(config)
    return verify_record(config, record)


def prune_backups(
    config: Config, *, now: Callable[[], datetime] = utcnow
) -> int:
    _prepare_destination(config, create=False)
    latest = _read_latest_record(config)
    verify_record(config, latest, now=now, enforce_age=False)
    records: list[BackupRecord] = []
    for manifest_path in config.backup_dir.glob("mydictionary-*.dump.json"):
        record = _record_from_payload(config, _read_json(manifest_path))
        if _manifest_path(record.path) != manifest_path:
            raise BackupError("Backup manifest filename mismatch")
        records.append(record)
    records.sort(key=lambda item: item.created_at, reverse=True)
    cutoff = now().astimezone(timezone.utc).timestamp() - (
        config.retention_days * 86400
    )
    candidates: list[BackupRecord] = []
    for index, record in enumerate(records):
        if index < config.minimum_backups or record.path == latest.path:
            continue
        if record.created_at.timestamp() >= cutoff:
            continue
        verify_record(config, record, now=now, enforce_age=False)
        candidates.append(record)
    for record in candidates:
        record.path.unlink()
        _manifest_path(record.path).unlink()
    deleted = len(candidates)
    LOGGER.info("Backup retention completed: deleted=%d", deleted)
    return deleted


def _run_locked(config: Config, action: Callable[[], Any]) -> Any:
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(config.lock_file, flags, 0o600)
    except OSError as exc:
        raise BackupError("Backup lock file is unsafe or unavailable") from exc
    try:
        os.fchmod(descriptor, 0o600)
        lock = os.fdopen(descriptor, "r+")
        descriptor = -1
        with lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise BackupError("Another backup operation is running") from exc
            return action()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Verify latest backup freshness, checksum, manifest, and archive format",
    )
    mode.add_argument(
        "--prune",
        action="store_true",
        help="Delete only verified backups beyond the retention and count floors",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )
    try:
        args = parse_args()
        config = Config.from_env()
        if args.check:
            _run_locked(config, lambda: verify_latest(config))
        elif args.prune:
            _run_locked(config, lambda: prune_backups(config))
        else:
            def create_from_runtime_connection() -> BackupRecord:
                with _database_url_libpq_environment(config):
                    return create_backup(config)

            _run_locked(config, create_from_runtime_connection)
        return 0
    except Exception as exc:
        LOGGER.error("Backup operation failed: error_type=%s", type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
