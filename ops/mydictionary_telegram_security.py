#!/usr/bin/env python3
"""Audit Telegram token leakage and create a private sanitized log copy."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import stat


TOKEN_PATTERN = re.compile(rb"[0-9]{5,12}:[A-Za-z0-9_-]{20,128}")
REDACTION = b"[REDACTED_BOT_TOKEN]"


class TelegramSecurityError(RuntimeError):
    """Raised when log auditing or copy creation would be unsafe."""


@dataclass(frozen=True)
class LogInspection:
    occurrences: int
    size_bytes: int


def _open_private_log(path: Path) -> tuple[int, int]:
    if not path.is_absolute():
        raise TelegramSecurityError("Log path must be absolute")
    if path.is_symlink():
        raise TelegramSecurityError("Log source cannot be a symlink")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise TelegramSecurityError("Log source cannot be opened safely") from exc
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode):
        os.close(descriptor)
        raise TelegramSecurityError("Log source must be a regular file")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        os.close(descriptor)
        raise TelegramSecurityError("Log source permissions must be 0600")
    return descriptor, metadata.st_size


def inspect_log(path: Path) -> LogInspection:
    descriptor, size_bytes = _open_private_log(Path(path))
    occurrences = 0
    with os.fdopen(descriptor, "rb") as handle:
        for line in handle:
            occurrences += len(TOKEN_PATTERN.findall(line))
    return LogInspection(occurrences=occurrences, size_bytes=size_bytes)


def _destination(path: Path) -> Path:
    if not path.is_absolute():
        raise TelegramSecurityError("Sanitized destination must be absolute")
    if path.exists() or path.is_symlink():
        raise TelegramSecurityError("Sanitized destination already exists")
    parent = path.parent
    if parent.is_symlink() or not parent.is_dir():
        raise TelegramSecurityError("Sanitized destination directory is unavailable")
    if stat.S_IMODE(parent.stat().st_mode) & 0o022:
        raise TelegramSecurityError(
            "Sanitized destination directory permissions are unsafe"
        )
    return path


def sanitize_copy(source_path: Path, destination_path: Path) -> LogInspection:
    destination = _destination(Path(destination_path))
    source_descriptor, source_size = _open_private_log(Path(source_path))
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    flags |= getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    occurrences = 0
    try:
        descriptor = os.open(destination, flags, 0o600)
    except BaseException:
        os.close(source_descriptor)
        raise
    try:
        with os.fdopen(source_descriptor, "rb") as source_handle, os.fdopen(
            descriptor, "wb"
        ) as destination_handle:
            for line in source_handle:
                sanitized, count = TOKEN_PATTERN.subn(REDACTION, line)
                occurrences += count
                destination_handle.write(sanitized)
            destination_handle.flush()
            os.fsync(destination_handle.fileno())
    except BaseException:
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        raise
    if destination.stat().st_mode & 0o077:
        raise TelegramSecurityError("Sanitized log permissions are unsafe")
    if inspect_log(destination).occurrences:
        raise TelegramSecurityError("Sanitized log still contains Telegram tokens")
    return LogInspection(occurrences=occurrences, size_bytes=source_size)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--log", type=Path, required=True)
    result.add_argument("--sanitize-to", type=Path)
    result.add_argument("--execute", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    if args.execute and args.sanitize_to is None:
        raise SystemExit("--execute requires --sanitize-to")
    if args.sanitize_to is not None and args.execute:
        inspection = sanitize_copy(args.log, args.sanitize_to)
        mode = "sanitized-copy"
    else:
        inspection = inspect_log(args.log)
        mode = "preview"
    print(
        json.dumps(
            {
                "mode": mode,
                "occurrences": inspection.occurrences,
                "size_bytes": inspection.size_bytes,
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
