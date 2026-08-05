#!/usr/bin/env python3
"""Deploy tested origin/main revisions to the local Mac mini release tree.

The unattended path is deliberately limited to code-only releases whose
Alembic head already matches production. Content or schema changes require the
explicit operator path so a database backup and recovery record exist before
state can change.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import fcntl
import hashlib
import io
import json
import logging
import os
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


LOGGER = logging.getLogger("mydictionary-autodeploy")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{1,127}$")
DATABASE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,63}$")
ACCESS_MODES = {"allowlist", "pilot", "public"}
ALLOWED_REPOSITORY_URLS = {
    "https://github.com/pirajoke/mydictionary.git",
    "git@github.com:pirajoke/mydictionary.git",
}
STATE_SCHEMA_VERSION = 1
SERVICE_TRANSITION_TIMEOUT_SECONDS = 15
SERVICE_TRANSITION_POLL_SECONDS = 0.1
PROTECTED_CONTENT_PREFIXES = ("content/",)
PROTECTED_CONTENT_NAMES = {
    "words.json",
    "words_vi.json",
    "words_ja.json",
}
SAFE_ENVIRONMENT_NAMES = (
    "HOME",
    "PATH",
    "LANG",
    "LC_ALL",
    "TMPDIR",
    "SSL_CERT_FILE",
    "SSL_CERT_DIR",
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


class DeploymentError(RuntimeError):
    """Base class for privacy-safe deployment failures."""


class ReadinessError(DeploymentError):
    """The candidate did not satisfy process and application readiness."""


class ManualRecoveryRequired(DeploymentError):
    """Automatic rollback would be unsafe after database state changed."""


class CandidateValidationError(DeploymentError):
    """The target revision failed deterministic release validation."""


@dataclass(frozen=True)
class Config:
    app_root: Path
    repository_url: str
    service_labels: tuple[str, ...]
    service_plists: tuple[Path, ...]
    bootstrap_python: Path
    database_url: str
    pg_dump_database: str | None
    pg_dump_binary: str
    pg_restore_binary: str
    health_url: str
    heartbeat_path: Path
    expected_access_mode: str
    heartbeat_max_age_seconds: int
    readiness_timeout_seconds: int
    readiness_consecutive_checks: int
    source_dir: Path
    releases_dir: Path
    current_link: Path
    deployed_state_file: Path
    holds_file: Path
    recovery_file: Path
    lock_file: Path
    config_file: Path
    backup_dir: Path

    @classmethod
    def from_env(cls, values: dict[str, str] | None = None) -> "Config":
        env = values if values is not None else os.environ
        app_root = Path(_required(env, "MYDICTIONARY_APP_ROOT")).expanduser().resolve()
        labels = tuple(
            value.strip()
            for value in _required(env, "MYDICTIONARY_SERVICE_LABELS").split(",")
            if value.strip()
        )
        if not labels or any(not LABEL_PATTERN.fullmatch(label) for label in labels):
            raise DeploymentError("Invalid MYDICTIONARY_SERVICE_LABELS")
        raw_plists = env.get("MYDICTIONARY_SERVICE_PLISTS", "").strip()
        if raw_plists:
            service_plists = tuple(
                Path(value.strip()).expanduser().resolve()
                for value in raw_plists.split(",")
                if value.strip()
            )
        else:
            service_plists = tuple(
                (Path.home() / "Library" / "LaunchAgents" / f"{label}.plist").resolve()
                for label in labels
            )
        if len(service_plists) != len(labels):
            raise DeploymentError("Service labels and plist paths must have equal length")

        health_url = env.get(
            "MYDICTIONARY_HEALTH_URL", "http://127.0.0.1:8791/health"
        ).strip()
        parsed_health = urlparse(health_url)
        if (
            parsed_health.scheme != "http"
            or parsed_health.hostname not in {"127.0.0.1", "localhost", "::1"}
            or not parsed_health.path
        ):
            raise DeploymentError("Health URL must be loopback HTTP")
        access_mode = env.get(
            "MYDICTIONARY_EXPECTED_ACCESS_MODE", "allowlist"
        ).strip().lower()
        if access_mode not in ACCESS_MODES:
            raise DeploymentError("Invalid expected access mode")
        max_age = _bounded_int(
            env,
            "MYDICTIONARY_HEARTBEAT_MAX_AGE_SECONDS",
            default=45,
            minimum=15,
            maximum=300,
        )
        timeout = _bounded_int(
            env,
            "MYDICTIONARY_READINESS_TIMEOUT_SECONDS",
            default=90,
            minimum=15,
            maximum=600,
        )
        consecutive = _bounded_int(
            env,
            "MYDICTIONARY_READINESS_CONSECUTIVE_CHECKS",
            default=3,
            minimum=2,
            maximum=10,
        )
        heartbeat_path = Path(
            env.get("MYDICTIONARY_HEARTBEAT_PATH", "").strip()
            or app_root / "bot-heartbeat.json"
        ).expanduser().resolve()
        repository_url = _required(env, "MYDICTIONARY_REPOSITORY_URL")
        if repository_url not in ALLOWED_REPOSITORY_URLS:
            raise DeploymentError("Unexpected MY DICTIONARY repository URL")
        database_url = _required(env, "DATABASE_URL")
        if not database_url.startswith(
            ("postgres://", "postgresql://", "postgresql+psycopg://")
        ):
            raise DeploymentError("Production deployer requires PostgreSQL")
        pg_dump_database = env.get("MYDICTIONARY_PGDUMP_DATABASE", "").strip()
        if pg_dump_database and not DATABASE_NAME_PATTERN.fullmatch(
            pg_dump_database
        ):
            raise DeploymentError(
                "MYDICTIONARY_PGDUMP_DATABASE must be a plain database name; "
                "use PGHOST, PGPORT, and PGUSER for connection settings"
            )
        return cls(
            app_root=app_root,
            repository_url=repository_url,
            service_labels=labels,
            service_plists=service_plists,
            bootstrap_python=Path(
                _required(env, "MYDICTIONARY_BOOTSTRAP_PYTHON")
            ).expanduser().resolve(),
            database_url=database_url,
            pg_dump_database=pg_dump_database or None,
            pg_dump_binary=env.get("MYDICTIONARY_PG_DUMP", "pg_dump").strip(),
            pg_restore_binary=env.get(
                "MYDICTIONARY_PG_RESTORE", "pg_restore"
            ).strip(),
            health_url=health_url,
            heartbeat_path=heartbeat_path,
            expected_access_mode=access_mode,
            heartbeat_max_age_seconds=max_age,
            readiness_timeout_seconds=timeout,
            readiness_consecutive_checks=consecutive,
            source_dir=app_root / ".deploy-source",
            releases_dir=app_root / "releases",
            current_link=app_root / "current",
            deployed_state_file=app_root / ".deployed-sha",
            holds_file=app_root / ".release-holds.json",
            recovery_file=app_root / ".deployment-recovery.json",
            lock_file=app_root / ".deploy.lock",
            config_file=app_root / "config.yaml",
            backup_dir=Path(
                env.get("MYDICTIONARY_BACKUP_DIR", "").strip()
                or app_root / "backups"
            ).expanduser().resolve(),
        )


@dataclass(frozen=True)
class ProbeResult:
    ready: bool
    reason: str


@dataclass(frozen=True)
class BackupRecord:
    path: Path
    digest_sha256: str
    database_revision: str
    target_revision: str


def _required(values: dict[str, str] | os._Environ[str], name: str) -> str:
    value = str(values.get(name) or "").strip()
    if not value:
        raise DeploymentError(f"Missing required setting: {name}")
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
        raise DeploymentError(f"{name} must be an integer") from exc
    if not minimum <= value <= maximum:
        raise DeploymentError(f"{name} is outside the allowed range")
    return value


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _selected_environment(names: tuple[str, ...]) -> dict[str, str]:
    return {name: os.environ[name] for name in names if os.environ.get(name)}


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    text: bool = True,
) -> subprocess.CompletedProcess:
    LOGGER.info("Running: %s", " ".join(command))
    return subprocess.run(
        command,
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=text,
    )


def validate_config(config: Config, *, require_plists: bool = False) -> None:
    if not config.app_root.is_dir():
        raise DeploymentError("Application root does not exist")
    if not config.bootstrap_python.is_file():
        raise DeploymentError("Bootstrap Python does not exist")
    if not config.config_file.is_file():
        raise DeploymentError("Bot config does not exist")
    if config.config_file.stat().st_mode & 0o077:
        raise DeploymentError("Bot config must not be group or world readable")
    if require_plists:
        missing = [path.name for path in config.service_plists if not path.is_file()]
        if missing:
            raise DeploymentError("Service plist is missing: " + ", ".join(missing))


def _atomic_write_text(path: Path, value: str) -> None:
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
            handle.write(value)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
        + "\n",
    )


def _read_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DeploymentError(f"Invalid state file: {path.name}") from exc
    if not isinstance(payload, dict):
        raise DeploymentError(f"Invalid state file: {path.name}")
    return payload


def ensure_source_checkout(config: Config) -> None:
    git_dir = config.source_dir / ".git"
    if not git_dir.is_dir():
        if config.source_dir.exists():
            raise DeploymentError("Deploy source is not a Git repository")
        run(
            [
                "git",
                "clone",
                "--filter=blob:none",
                "--no-checkout",
                config.repository_url,
                str(config.source_dir),
            ]
        )
    remote = run(
        ["git", "-C", str(config.source_dir), "remote", "get-url", "origin"]
    ).stdout.strip()
    if remote != config.repository_url:
        raise DeploymentError("Unexpected deploy source origin")
    run(
        [
            "git",
            "-C",
            str(config.source_dir),
            "fetch",
            "--prune",
            "origin",
            "main",
        ]
    )


def main_sha(config: Config) -> str:
    value = run(
        ["git", "-C", str(config.source_dir), "rev-parse", "origin/main"]
    ).stdout.strip()
    if not SHA_PATTERN.fullmatch(value):
        raise DeploymentError("origin/main did not resolve to a commit SHA")
    return value


def deployed_sha(config: Config) -> str | None:
    try:
        value = config.deployed_state_file.read_text(encoding="ascii").strip()
    except FileNotFoundError:
        return None
    if not SHA_PATTERN.fullmatch(value):
        raise DeploymentError("Invalid deployed SHA state")
    return value


def current_target(config: Config) -> Path | None:
    if config.current_link.is_symlink():
        target = config.current_link.resolve()
        releases_dir = config.releases_dir.resolve()
        if (
            target.parent != releases_dir
            or not SHA_PATTERN.fullmatch(target.name)
            or not target.is_dir()
        ):
            raise DeploymentError("Current symlink is not a versioned release")
        return target
    if config.current_link.exists():
        raise DeploymentError("Current path is not a symlink")
    return None


def is_fast_forward(config: Config, old_sha: str, new_sha: str) -> bool:
    result = subprocess.run(
        [
            "git",
            "-C",
            str(config.source_dir),
            "merge-base",
            "--is-ancestor",
            old_sha,
            new_sha,
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode not in (0, 1):
        raise DeploymentError("Unable to validate main history")
    return result.returncode == 0


def changed_paths(config: Config, old_sha: str, new_sha: str) -> tuple[str, ...]:
    output = run(
        [
            "git",
            "-C",
            str(config.source_dir),
            "diff",
            "--name-only",
            old_sha,
            new_sha,
        ]
    ).stdout
    return tuple(path for path in output.splitlines() if path)


def protected_content_changes(paths: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        path
        for path in paths
        if path in PROTECTED_CONTENT_NAMES
        or path.startswith(PROTECTED_CONTENT_PREFIXES)
        or (path.startswith("words_") and path.endswith(".json"))
    )


def safe_extract(archive: bytes, destination: Path) -> None:
    with tarfile.open(fileobj=io.BytesIO(archive), mode="r:") as bundle:
        for member in bundle.getmembers():
            if not (member.isfile() or member.isdir()):
                raise CandidateValidationError(
                    "Release archive contains a special file or link"
                )
            target = (destination / member.name).resolve()
            if destination.resolve() not in (target, *target.parents):
                raise CandidateValidationError("Release archive contains an unsafe path")
        bundle.extractall(destination)


def build_release(config: Config, sha: str) -> Path:
    release = config.releases_dir / sha
    if release.is_dir() and not release.is_symlink():
        return release
    if release.exists() or release.is_symlink():
        raise CandidateValidationError("Release path is not a regular directory")
    config.releases_dir.mkdir(parents=True, exist_ok=True)
    temporary = Path(
        tempfile.mkdtemp(prefix=f".{sha[:12]}-", dir=config.releases_dir)
    )
    try:
        archive = run(
            ["git", "-C", str(config.source_dir), "archive", "--format=tar", sha],
            text=False,
        ).stdout
        safe_extract(archive, temporary)
        for filename in (
            "bot.py",
            "tts.py",
            "requirements.txt",
            "requirements.lock",
            "alembic.ini",
        ):
            if not (temporary / filename).is_file():
                raise CandidateValidationError(
                    f"Release is missing required file: {filename}"
                )
        if (temporary / "config.yaml").exists():
            raise CandidateValidationError(
                "Repository release must not contain config.yaml"
            )

        venv_dir = temporary / ".venv"
        build_env = _selected_environment(SAFE_ENVIRONMENT_NAMES)
        run(
            [str(config.bootstrap_python), "-m", "venv", str(venv_dir)],
            env=build_env,
        )
        release_python = venv_dir / "bin" / "python3"
        run(
            [
                str(release_python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "--requirement",
                str(temporary / "requirements.lock"),
            ],
            env=build_env,
        )
        test_data_dir = temporary / ".test-data"
        test_data_dir.mkdir(mode=0o700)
        os.chmod(test_data_dir, 0o700)
        test_env = _selected_environment(SAFE_ENVIRONMENT_NAMES)
        test_env.update(
            {
                "ALLOWED_USER_ID": "1",
                "ALLOW_SQLITE_DEV": "true",
                "BOT_TOKEN": "123456:AUTODEPLOYTEST",
                "DATA_DIR": str(test_data_dir),
                "DATABASE_URL": f"sqlite:///{test_data_dir / 'candidate-tests.db'}",
                "PYTHONDONTWRITEBYTECODE": "1",
            }
        )
        try:
            run(
                [
                    str(release_python),
                    "-m",
                    "unittest",
                    "discover",
                    "-s",
                    "tests",
                    "-v",
                ],
                cwd=temporary,
                env=test_env,
            )
            run(
                [str(release_python), "-m", "compileall", "-q", "."],
                cwd=temporary,
                env=test_env,
            )
        except subprocess.CalledProcessError as exc:
            raise CandidateValidationError(
                "Candidate tests or compilation failed"
            ) from exc
        shutil.rmtree(test_data_dir, ignore_errors=True)
        (temporary / "config.yaml").symlink_to(config.config_file)
        temporary.rename(release)
        return release
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def release_python(release: Path) -> Path:
    python = release / ".venv" / "bin" / "python3"
    if not python.is_file():
        raise DeploymentError("Release Python is missing")
    return python


def migration_head(release: Path) -> str:
    script = """
from pathlib import Path
from alembic.config import Config
from alembic.script import ScriptDirectory
root = Path.cwd()
config = Config(str(root / 'alembic.ini'))
config.set_main_option('script_location', str(root / 'migrations'))
heads = ScriptDirectory.from_config(config).get_heads()
if len(heads) != 1:
    raise SystemExit('expected exactly one Alembic head')
print(heads[0])
""".strip()
    try:
        value = run(
            [str(release_python(release)), "-c", script],
            cwd=release,
            env=_selected_environment(SAFE_ENVIRONMENT_NAMES),
        ).stdout.strip()
    except subprocess.CalledProcessError as exc:
        raise CandidateValidationError("Unable to resolve candidate migration head") from exc
    if not value or any(character.isspace() for character in value):
        raise CandidateValidationError("Invalid candidate migration head")
    return value


def _database_env(config: Config) -> dict[str, str]:
    environment = _selected_environment(SAFE_ENVIRONMENT_NAMES)
    environment["DATABASE_URL"] = config.database_url
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return environment


def database_revision(config: Config, release: Path) -> str:
    script = """
import os
from sqlalchemy import create_engine, text
url = os.environ['DATABASE_URL']
if url.startswith('postgres://'):
    url = url.replace('postgres://', 'postgresql+psycopg://', 1)
elif url.startswith('postgresql://'):
    url = url.replace('postgresql://', 'postgresql+psycopg://', 1)
engine = create_engine(url)
try:
    with engine.connect() as connection:
        values = list(
            connection.execute(
                text('select version_num from alembic_version')
            ).scalars()
        )
finally:
    engine.dispose()
if len(values) != 1:
    raise SystemExit('expected exactly one database revision')
print(values[0])
""".strip()
    value = run(
        [str(release_python(release)), "-c", script],
        cwd=release,
        env=_database_env(config),
    ).stdout.strip()
    if not value or any(character.isspace() for character in value):
        raise DeploymentError("Invalid database revision")
    return value


def apply_migrations(config: Config, release: Path) -> None:
    script = """
import os
from mydictionary.storage import run_migrations
run_migrations(os.environ['DATABASE_URL'])
""".strip()
    run(
        [str(release_python(release)), "-c", script],
        cwd=release,
        env=_database_env(config),
    )


def activate_release(config: Config, release: Path) -> None:
    temporary = config.app_root / f".current-{os.getpid()}"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(release, target_is_directory=True)
    os.replace(temporary, config.current_link)


def restart_services(config: Config) -> None:
    domain = f"gui/{os.getuid()}"
    for label in config.service_labels:
        run(["launchctl", "kickstart", "-k", f"{domain}/{label}"])


def service_is_loaded(label: str) -> bool:
    result = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def wait_for_service_registration(
    label: str,
    *,
    loaded: bool,
    timeout_seconds: float | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    timeout = (
        SERVICE_TRANSITION_TIMEOUT_SECONDS
        if timeout_seconds is None
        else timeout_seconds
    )
    deadline = time.monotonic() + timeout
    while True:
        if service_is_loaded(label) is loaded:
            return
        if time.monotonic() >= deadline:
            expected = "loaded" if loaded else "unloaded"
            raise DeploymentError(
                f"Service registration did not become {expected}: {label}"
            )
        sleep(SERVICE_TRANSITION_POLL_SECONDS)


def _unload_service(label: str) -> None:
    domain = f"gui/{os.getuid()}"
    try:
        result = subprocess.run(
            ["launchctl", "bootout", f"{domain}/{label}"],
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise DeploymentError(f"Unable to stop service: {label}") from exc
    if result.returncode != 0:
        if not service_is_loaded(label):
            return
        raise DeploymentError(f"Unable to stop service: {label}")
    wait_for_service_registration(label, loaded=False)


def stop_services(config: Config) -> None:
    failed: list[str] = []
    for label in reversed(config.service_labels):
        try:
            _unload_service(label)
        except DeploymentError:
            failed.append(label)
    if failed:
        raise DeploymentError("Unable to stop services: " + ", ".join(failed))


def bootstrap_services(config: Config) -> None:
    domain = f"gui/{os.getuid()}"
    for label, plist in zip(config.service_labels, config.service_plists):
        if service_is_loaded(label):
            _unload_service(label)
        run(["launchctl", "bootstrap", domain, str(plist)])
        wait_for_service_registration(label, loaded=True)


def service_is_running(label: str) -> bool:
    result = subprocess.run(
        ["launchctl", "print", f"gui/{os.getuid()}/{label}"],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and "state = running" in result.stdout


def _http_health(url: str) -> bool:
    request = Request(url, headers={"User-Agent": "mydictionary-deployer/1"})
    try:
        with urlopen(request, timeout=5) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read(2048).decode("utf-8"))
    except (HTTPError, URLError, OSError, UnicodeError, json.JSONDecodeError):
        return False
    return payload == {"status": "ok"}


def _heartbeat_ready(config: Config, expected_sha: str) -> ProbeResult:
    try:
        payload = json.loads(config.heartbeat_path.read_text(encoding="utf-8"))
        observed = datetime.fromisoformat(str(payload["heartbeat_at"]))
        if observed.tzinfo is None:
            raise ValueError
        age = (utcnow() - observed.astimezone(timezone.utc)).total_seconds()
    except (
        FileNotFoundError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
    ):
        return ProbeResult(False, "heartbeat_invalid")
    if payload.get("schema_version") != 1 or payload.get("state") != "ready":
        return ProbeResult(False, "heartbeat_not_ready")
    if age < -5 or age > config.heartbeat_max_age_seconds:
        return ProbeResult(False, "heartbeat_stale")
    if payload.get("release_sha") != expected_sha:
        return ProbeResult(False, "release_mismatch")
    if payload.get("access_mode") != config.expected_access_mode:
        return ProbeResult(False, "access_mode_mismatch")
    return ProbeResult(True, "ready")


def readiness_probe(config: Config, expected_sha: str) -> ProbeResult:
    if not all(service_is_running(label) for label in config.service_labels):
        return ProbeResult(False, "service_not_running")
    heartbeat = _heartbeat_ready(config, expected_sha)
    if not heartbeat.ready:
        return heartbeat
    if not _http_health(config.health_url):
        return ProbeResult(False, "http_unhealthy")
    return ProbeResult(True, "ready")


def wait_for_readiness(
    config: Config,
    expected_sha: str,
    *,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    deadline = time.monotonic() + config.readiness_timeout_seconds
    consecutive = 0
    last_reason = "not_checked"
    while time.monotonic() < deadline:
        probe = readiness_probe(config, expected_sha)
        last_reason = probe.reason
        if probe.ready:
            consecutive += 1
            if consecutive >= config.readiness_consecutive_checks:
                return
        else:
            consecutive = 0
        sleep(2)
    raise ReadinessError(f"Candidate readiness failed: {last_reason}")


def _hold_state(config: Config) -> dict[str, Any]:
    state = _read_json(
        config.holds_file,
        {"schema_version": STATE_SCHEMA_VERSION, "releases": {}},
    )
    if state.get("schema_version") != STATE_SCHEMA_VERSION or not isinstance(
        state.get("releases"), dict
    ):
        raise DeploymentError("Invalid release hold state")
    return state


def release_hold(config: Config, sha: str) -> dict[str, Any] | None:
    value = _hold_state(config)["releases"].get(sha)
    return value if isinstance(value, dict) else None


def record_hold(
    config: Config,
    sha: str,
    *,
    kind: str,
    stage: str,
    error_type: str,
    previous_sha: str | None,
) -> None:
    state = _hold_state(config)
    state["releases"][sha] = {
        "kind": kind,
        "stage": stage,
        "error_type": error_type,
        "previous_sha": previous_sha,
        "recorded_at": utcnow().isoformat(),
    }
    _atomic_write_json(config.holds_file, state)


def clear_hold(config: Config, sha: str, *, failed_only: bool = False) -> bool:
    state = _hold_state(config)
    existing = state["releases"].get(sha)
    if not isinstance(existing, dict):
        return False
    if failed_only and existing.get("kind") != "failed":
        raise DeploymentError("Only failed releases can be cleared with this command")
    del state["releases"][sha]
    _atomic_write_json(config.holds_file, state)
    return True


def _run_with_state_lock(config: Config, action: Callable[[], str]) -> str:
    config.lock_file.touch(mode=0o600, exist_ok=True)
    os.chmod(config.lock_file, 0o600)
    with config.lock_file.open("r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise DeploymentError("Another deployment is already running") from exc
        return action()


def clear_failed_quarantine(config: Config, sha: str) -> str:
    def clear() -> str:
        if not clear_hold(config, sha, failed_only=True):
            raise DeploymentError("No failed quarantine exists for that SHA")
        return sha

    return _run_with_state_lock(config, clear)


def write_deployed_state(config: Config, sha: str) -> None:
    if not SHA_PATTERN.fullmatch(sha):
        raise DeploymentError("Invalid deployed SHA")
    _atomic_write_text(config.deployed_state_file, f"{sha}\n")


def write_recovery_state(config: Config, payload: dict[str, Any]) -> None:
    value = {
        "schema_version": STATE_SCHEMA_VERSION,
        "updated_at": utcnow().isoformat(),
        **payload,
    }
    _atomic_write_json(config.recovery_file, value)


def backup_database(
    config: Config,
    *,
    target_sha: str,
    database_revision_value: str,
    target_revision: str,
) -> BackupRecord:
    if not config.pg_dump_database:
        raise DeploymentError("MYDICTIONARY_PGDUMP_DATABASE is required")
    config.backup_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(config.backup_dir, 0o700)
    timestamp = utcnow().strftime("%Y%m%dT%H%M%S.%fZ")
    final_path = config.backup_dir / f"mydictionary-{timestamp}-{target_sha[:12]}.dump"
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=config.backup_dir,
            prefix=f".{final_path.name}.",
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
        os.chmod(temporary, 0o600)
        environment = _selected_environment(
            SAFE_ENVIRONMENT_NAMES + LIBPQ_ENVIRONMENT_NAMES
        )
        environment["PGDATABASE"] = config.pg_dump_database
        run(
            [
                config.pg_dump_binary,
                "-Fc",
                "--no-owner",
                "--no-privileges",
                "--file",
                str(temporary),
            ],
            env=environment,
        )
        run([config.pg_restore_binary, "--list", str(temporary)])
        if temporary.stat().st_size <= 0:
            raise DeploymentError("Database backup is empty")
        digest = _sha256_file(temporary)
        if final_path.exists():
            raise DeploymentError("Database backup path already exists")
        os.replace(temporary, final_path)
        temporary = None
        return BackupRecord(
            path=final_path,
            digest_sha256=digest,
            database_revision=database_revision_value,
            target_revision=target_revision,
        )
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def _recovery_payload(
    *,
    status: str,
    target_sha: str,
    previous_sha: str | None,
    previous_revision: str,
    target_revision: str,
    backup: BackupRecord | None,
    stage: str,
) -> dict[str, Any]:
    return {
        "status": status,
        "target_sha": target_sha,
        "previous_sha": previous_sha,
        "previous_revision": previous_revision,
        "target_revision": target_revision,
        "backup_file": backup.path.name if backup else None,
        "backup_sha256": backup.digest_sha256 if backup else None,
        "stage": stage,
    }


def _manual_recovery_completion(
    config: Config,
    *,
    target_sha: str,
    target_revision: str,
) -> dict[str, Any] | None:
    if not config.recovery_file.exists():
        return None
    state = _read_json(config.recovery_file, {})
    if state.get("schema_version") != STATE_SCHEMA_VERSION:
        raise DeploymentError("Invalid deployment recovery state")
    if state.get("status") != "manual_recovery_required":
        return None
    if state.get("target_sha") != target_sha:
        raise DeploymentError("Recovery target does not match current release")
    if state.get("target_revision") != target_revision:
        raise DeploymentError("Recovery revision does not match current database")

    previous_sha = state.get("previous_sha")
    if previous_sha is not None and (
        not isinstance(previous_sha, str)
        or not SHA_PATTERN.fullmatch(previous_sha)
    ):
        raise DeploymentError("Invalid deployment recovery state")
    previous_revision = state.get("previous_revision")
    if not isinstance(previous_revision, str) or not previous_revision:
        raise DeploymentError("Invalid deployment recovery state")

    backup_file = state.get("backup_file")
    backup_sha256 = state.get("backup_sha256")
    backup: BackupRecord | None = None
    if backup_file is None and backup_sha256 is None:
        pass
    elif (
        isinstance(backup_file, str)
        and backup_file
        and Path(backup_file).name == backup_file
        and isinstance(backup_sha256, str)
        and re.fullmatch(r"[0-9a-f]{64}", backup_sha256)
    ):
        backup_path = config.backup_dir / backup_file
        if backup_path.is_symlink() or not backup_path.is_file():
            raise DeploymentError("Recovery backup is unavailable")
        if _sha256_file(backup_path) != backup_sha256:
            raise DeploymentError("Recovery backup digest does not match")
        run([config.pg_restore_binary, "--list", str(backup_path)])
        backup = BackupRecord(
            path=backup_path,
            digest_sha256=backup_sha256,
            database_revision=previous_revision,
            target_revision=target_revision,
        )
    else:
        raise DeploymentError("Invalid deployment recovery state")

    return _recovery_payload(
        status="completed",
        target_sha=target_sha,
        previous_sha=previous_sha,
        previous_revision=previous_revision,
        target_revision=target_revision,
        backup=backup,
        stage="ready_after_manual_adopt",
    )


def _automatic_deploy(
    config: Config,
    *,
    target_sha: str,
    previous_sha: str | None,
    previous_release: Path | None,
    release: Path,
    previous_revision: str,
) -> str:
    activate_release(config, release)
    try:
        restart_services(config)
        wait_for_readiness(config, target_sha)
    except Exception as exc:
        record_hold(
            config,
            target_sha,
            kind="failed",
            stage="readiness",
            error_type=type(exc).__name__,
            previous_sha=previous_sha,
        )
        try:
            observed_revision = database_revision(config, release)
        except Exception as revision_exc:
            write_recovery_state(
                config,
                _recovery_payload(
                    status="manual_recovery_required",
                    target_sha=target_sha,
                    previous_sha=previous_sha,
                    previous_revision=previous_revision,
                    target_revision="unknown",
                    backup=None,
                    stage="readiness_database_probe_failed",
                ),
            )
            raise ManualRecoveryRequired(
                "Database revision is unknown; automatic rollback refused"
            ) from revision_exc
        if (
            observed_revision != previous_revision
            or previous_release is None
            or previous_sha is None
        ):
            write_recovery_state(
                config,
                _recovery_payload(
                    status="manual_recovery_required",
                    target_sha=target_sha,
                    previous_sha=previous_sha,
                    previous_revision=previous_revision,
                    target_revision=observed_revision,
                    backup=None,
                    stage="readiness_database_changed",
                ),
            )
            raise ManualRecoveryRequired(
                "Database state changed or previous release is unknown; automatic rollback refused"
            ) from exc
        try:
            activate_release(config, previous_release)
            restart_services(config)
            wait_for_readiness(config, previous_sha)
        except Exception as rollback_exc:
            write_recovery_state(
                config,
                _recovery_payload(
                    status="manual_recovery_required",
                    target_sha=target_sha,
                    previous_sha=previous_sha,
                    previous_revision=previous_revision,
                    target_revision=observed_revision,
                    backup=None,
                    stage="automatic_rollback_failed",
                ),
            )
            raise ManualRecoveryRequired(
                "Previous release did not recover readiness"
            ) from rollback_exc
        raise
    write_deployed_state(config, target_sha)
    clear_hold(config, target_sha)
    LOGGER.info("Deployment completed: %s", target_sha)
    return target_sha


def _operator_migration_deploy(
    config: Config,
    *,
    target_sha: str,
    previous_sha: str | None,
    previous_release: Path | None,
    release: Path,
    previous_revision: str,
    target_revision: str,
) -> str:
    validate_config(config, require_plists=True)
    try:
        stop_services(config)
    except Exception as stop_exc:
        try:
            bootstrap_services(config)
            if previous_sha:
                wait_for_readiness(config, previous_sha)
        except Exception as recovery_exc:
            record_hold(
                config,
                target_sha,
                kind="failed",
                stage="operator_stop",
                error_type=type(stop_exc).__name__,
                previous_sha=previous_sha,
            )
            write_recovery_state(
                config,
                _recovery_payload(
                    status="manual_recovery_required",
                    target_sha=target_sha,
                    previous_sha=previous_sha,
                    previous_revision=previous_revision,
                    target_revision=target_revision,
                    backup=None,
                    stage="service_stop_recovery_failed",
                ),
            )
            raise ManualRecoveryRequired(
                "Services could not be safely stopped or restored"
            ) from recovery_exc
        raise

    backup: BackupRecord | None = None
    try:
        backup = backup_database(
            config,
            target_sha=target_sha,
            database_revision_value=previous_revision,
            target_revision=target_revision,
        )
        write_recovery_state(
            config,
            _recovery_payload(
                status="in_progress",
                target_sha=target_sha,
                previous_sha=previous_sha,
                previous_revision=previous_revision,
                target_revision=target_revision,
                backup=backup,
                stage="backup_created",
            ),
        )
        activate_release(config, release)
    except Exception as pre_migration_exc:
        try:
            if previous_release is None or previous_sha is None:
                raise DeploymentError("Previous release is unavailable")
            activate_release(config, previous_release)
            bootstrap_services(config)
            wait_for_readiness(config, previous_sha)
        except Exception as recovery_exc:
            record_hold(
                config,
                target_sha,
                kind="operator_required",
                stage="operator_pre_migration_retry",
                error_type=type(pre_migration_exc).__name__,
                previous_sha=previous_sha,
            )
            write_recovery_state(
                config,
                _recovery_payload(
                    status="manual_recovery_required",
                    target_sha=target_sha,
                    previous_sha=previous_sha,
                    previous_revision=previous_revision,
                    target_revision=target_revision,
                    backup=backup,
                    stage="pre_migration_recovery_failed",
                ),
            )
            raise ManualRecoveryRequired(
                "Pre-migration failure did not recover the previous release"
            ) from recovery_exc
        record_hold(
            config,
            target_sha,
            kind="operator_required",
            stage="operator_pre_migration_retry",
            error_type=type(pre_migration_exc).__name__,
            previous_sha=previous_sha,
        )
        write_recovery_state(
            config,
            _recovery_payload(
                status="recovered",
                target_sha=target_sha,
                previous_sha=previous_sha,
                previous_revision=previous_revision,
                target_revision=target_revision,
                backup=backup,
                stage="pre_migration_failure_recovered",
            ),
        )
        raise

    try:
        apply_migrations(config, release)
        observed_revision = database_revision(config, release)
        if observed_revision != target_revision:
            raise DeploymentError("Database did not reach the candidate migration head")
        write_recovery_state(
            config,
            _recovery_payload(
                status="in_progress",
                target_sha=target_sha,
                previous_sha=previous_sha,
                previous_revision=previous_revision,
                target_revision=target_revision,
                backup=backup,
                stage="migration_applied",
            ),
        )
        bootstrap_services(config)
        wait_for_readiness(config, target_sha)
    except Exception as exc:
        recovery_stage = "migration_or_readiness_failed_contained"
        try:
            stop_services(config)
        except Exception:
            recovery_stage = "post_migration_containment_failed"
        record_hold(
            config,
            target_sha,
            kind="failed",
            stage="operator_migration",
            error_type=type(exc).__name__,
            previous_sha=previous_sha,
        )
        write_recovery_state(
            config,
            _recovery_payload(
                status="manual_recovery_required",
                target_sha=target_sha,
                previous_sha=previous_sha,
                previous_revision=previous_revision,
                target_revision=target_revision,
                backup=backup,
                stage=recovery_stage,
            ),
        )
        raise ManualRecoveryRequired(
            "Migration started; automatic code or database rollback refused"
        ) from exc

    write_deployed_state(config, target_sha)
    clear_hold(config, target_sha)
    write_recovery_state(
        config,
        _recovery_payload(
            status="completed",
            target_sha=target_sha,
            previous_sha=previous_sha,
            previous_revision=previous_revision,
            target_revision=target_revision,
            backup=backup,
            stage="ready",
        ),
    )
    LOGGER.info("Operator migration deployment completed: %s", target_sha)
    return target_sha


def deploy(
    config: Config,
    *,
    operator: bool = False,
    prepare_only: bool = False,
) -> str:
    validate_config(config)
    config.lock_file.touch(mode=0o600, exist_ok=True)
    os.chmod(config.lock_file, 0o600)
    with config.lock_file.open("r+") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            LOGGER.info("Another deployment is already running")
            return "locked"

        ensure_source_checkout(config)
        target_sha = main_sha(config)
        previous_sha = deployed_sha(config)
        previous_release = current_target(config)
        if (previous_sha is None) != (previous_release is None):
            raise DeploymentError("Deployed SHA and current release state disagree")
        if (
            previous_sha is not None
            and previous_release != config.releases_dir / previous_sha
        ):
            raise DeploymentError("Current release does not match deployed SHA")
        if previous_sha == target_sha and previous_release == config.releases_dir / target_sha:
            LOGGER.info("Already deployed: %s", target_sha)
            return target_sha
        hold = release_hold(config, target_sha)
        if hold and not (operator and hold.get("kind") == "operator_required"):
            LOGGER.warning(
                "Release held: sha=%s kind=%s stage=%s",
                target_sha,
                hold.get("kind", "unknown"),
                hold.get("stage", "unknown"),
            )
            return "held"
        if previous_sha and not is_fast_forward(config, previous_sha, target_sha):
            raise DeploymentError("origin/main is not a fast-forward")

        paths = changed_paths(config, previous_sha, target_sha) if previous_sha else ()
        protected = protected_content_changes(paths)
        try:
            release = build_release(config, target_sha)
        except CandidateValidationError as exc:
            record_hold(
                config,
                target_sha,
                kind="failed",
                stage="candidate_validation",
                error_type=type(exc).__name__,
                previous_sha=previous_sha,
            )
            raise
        if prepare_only:
            LOGGER.info("Prepared release without activation: %s", target_sha)
            return target_sha

        try:
            target_revision = migration_head(release)
        except CandidateValidationError as exc:
            record_hold(
                config,
                target_sha,
                kind="failed",
                stage="migration_metadata",
                error_type=type(exc).__name__,
                previous_sha=previous_sha,
            )
            raise
        previous_revision = database_revision(config, release)
        migration_required = target_revision != previous_revision
        if (protected or migration_required) and not operator:
            stage = "migration_required" if migration_required else "content_review_required"
            record_hold(
                config,
                target_sha,
                kind="operator_required",
                stage=stage,
                error_type="OperatorApprovalRequired",
                previous_sha=previous_sha,
            )
            LOGGER.warning(
                "Release requires operator deployment: sha=%s stage=%s",
                target_sha,
                stage,
            )
            return "held"
        if migration_required:
            return _operator_migration_deploy(
                config,
                target_sha=target_sha,
                previous_sha=previous_sha,
                previous_release=previous_release,
                release=release,
                previous_revision=previous_revision,
                target_revision=target_revision,
            )
        return _automatic_deploy(
            config,
            target_sha=target_sha,
            previous_sha=previous_sha,
            previous_release=previous_release,
            release=release,
            previous_revision=previous_revision,
        )


def adopt_current_release(config: Config) -> str:
    validate_config(config)

    def adopt() -> str:
        ensure_source_checkout(config)
        target_sha = main_sha(config)
        release = config.releases_dir / target_sha
        if current_target(config) != release:
            raise DeploymentError("Current release does not match origin/main")
        observed_revision = database_revision(config, release)
        if observed_revision != migration_head(release):
            raise DeploymentError("Database revision does not match current release")
        wait_for_readiness(config, target_sha)
        recovery = _manual_recovery_completion(
            config,
            target_sha=target_sha,
            target_revision=observed_revision,
        )
        write_deployed_state(config, target_sha)
        if recovery is not None:
            write_recovery_state(config, recovery)
        clear_hold(config, target_sha)
        LOGGER.info("Adopted running release: %s", target_sha)
        return target_sha

    return _run_with_state_lock(config, adopt)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--prepare-only",
        action="store_true",
        help="Build and test origin/main without activating or restarting it",
    )
    mode.add_argument(
        "--operator-deploy",
        action="store_true",
        help="Allow reviewed content and migrations with backup and fail-closed recovery",
    )
    mode.add_argument(
        "--adopt-current",
        action="store_true",
        help="Record an already-running healthy origin/main release",
    )
    mode.add_argument(
        "--clear-failed",
        metavar="SHA",
        help="Clear one failed-SHA quarantine after operator review",
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
        if args.clear_failed:
            if not SHA_PATTERN.fullmatch(args.clear_failed):
                raise DeploymentError("Invalid SHA for --clear-failed")
            clear_failed_quarantine(config, args.clear_failed)
        elif args.adopt_current:
            adopt_current_release(config)
        else:
            deploy(
                config,
                operator=args.operator_deploy,
                prepare_only=args.prepare_only,
            )
        return 0
    except Exception as exc:
        LOGGER.error("Deployment failed: error_type=%s", type(exc).__name__)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
