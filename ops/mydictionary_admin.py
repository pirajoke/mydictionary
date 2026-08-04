#!/usr/bin/env python3
"""Start the admin server from the active MY DICTIONARY release."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat


SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")


def required(values: dict[str, str], name: str) -> str:
    value = str(values.get(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required setting: {name}")
    return value


def required_secret(values: dict[str, object], name: str) -> str:
    raw_value = values.get(name)
    if not isinstance(raw_value, str):
        raise RuntimeError(f"Missing admin secret: {name}")
    value = raw_value.strip()
    if not value:
        raise RuntimeError(f"Missing admin secret: {name}")
    return value


def active_release(current: Path) -> Path:
    if not current.is_symlink():
        raise RuntimeError("Current release path must be a symlink")
    release = current.resolve()
    if release.parent != (current.parent / "releases").resolve():
        raise RuntimeError("Current release must stay inside the versioned release tree")
    if not SHA_PATTERN.fullmatch(release.name) or not release.is_dir():
        raise RuntimeError("Current release directory is not a commit SHA")
    return release


def active_release_sha(current: Path) -> str:
    return active_release(current).name


def build_process(
    values: dict[str, str] | None = None,
) -> tuple[Path, list[str], dict[str, str], Path]:
    source = dict(os.environ if values is None else values)
    app_root = Path(required(source, "MYDICTIONARY_APP_ROOT")).expanduser().resolve()
    current = app_root / "current"
    secrets_path = Path(
        source.get("MYDICTIONARY_ADMIN_SECRETS", "").strip()
        or app_root / "admin-secrets.json"
    ).expanduser().resolve()
    secrets = json.loads(secrets_path.read_text(encoding="utf-8"))
    if not isinstance(secrets, dict):
        raise RuntimeError("Admin secrets file must contain an object")
    if stat.S_IMODE(secrets_path.stat().st_mode) & 0o077:
        raise RuntimeError("Admin secrets file must not be group or world readable")
    release = active_release(current)
    release_sha = release.name
    release_python = release / ".venv" / "bin" / "python3"
    if not release_python.is_file():
        raise RuntimeError("Release Python is missing")

    environment = {
        key: source[key]
        for key in ("HOME", "PATH", "LANG", "LC_ALL", "TMPDIR")
        if source.get(key)
    }
    database_url = required(source, "DATABASE_URL")
    if not database_url.startswith(
        ("postgres://", "postgresql://", "postgresql+psycopg://")
    ):
        raise RuntimeError("Admin launcher requires PostgreSQL")
    environment.update(
        {
            "PYTHONUNBUFFERED": "1",
            "DATABASE_URL": database_url,
            "DATA_DIR": str(app_root),
            "ADMIN_USERNAME": required_secret(secrets, "username"),
            "ADMIN_PASSWORD_HASH": required_secret(secrets, "password_hash"),
            "ADMIN_SESSION_SECRET": required_secret(secrets, "session_secret"),
            "ADMIN_HOST": source.get("ADMIN_HOST", "127.0.0.1").strip(),
            "ADMIN_PORT": source.get("ADMIN_PORT", "8791").strip(),
            "ADMIN_COOKIE_SECURE": source.get(
                "ADMIN_COOKIE_SECURE", "true"
            ).strip(),
            "AI_TUTOR_ENABLED": source.get("AI_TUTOR_ENABLED", "false").strip(),
            "AI_INITIAL_CREDITS": source.get("AI_INITIAL_CREDITS", "0").strip(),
            "RELEASE_SHA": release_sha,
        }
    )
    if len(environment["ADMIN_SESSION_SECRET"]) < 32:
        raise RuntimeError("Admin session secret must contain at least 32 characters")
    if environment["ADMIN_HOST"] not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("Admin host must remain loopback")
    if environment["AI_TUTOR_ENABLED"].lower() not in {"0", "false", "no", "off"}:
        raise RuntimeError("Versioned admin launcher refuses to enable AI")
    if environment["ADMIN_COOKIE_SECURE"].lower() not in {
        "0",
        "1",
        "false",
        "true",
        "no",
        "yes",
        "off",
        "on",
    }:
        raise RuntimeError("ADMIN_COOKIE_SECURE must be a boolean")
    try:
        port = int(environment["ADMIN_PORT"])
    except ValueError as exc:
        raise RuntimeError("ADMIN_PORT must be an integer") from exc
    if not 1024 <= port <= 65535:
        raise RuntimeError("ADMIN_PORT is outside the allowed range")

    arguments = [
        str(release_python),
        "-m",
        "gunicorn",
        "--workers",
        "1",
        "--threads",
        "4",
        "--bind",
        f"{environment['ADMIN_HOST']}:{port}",
        "--access-logfile",
        "-",
        "--error-logfile",
        "-",
        "mydictionary.admin:create_app()",
    ]
    return release_python, arguments, environment, release


def main() -> None:
    executable, arguments, environment, working_directory = build_process()
    os.chdir(working_directory)
    os.execve(str(executable), arguments, environment)


if __name__ == "__main__":
    main()
