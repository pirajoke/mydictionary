"""Privacy-minimized fallback journal for provider metering failures."""

from __future__ import annotations

import fcntl
from datetime import datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Callable, Mapping


ALLOWED_FIELDS = {
    "request_id",
    "provider_response_id",
    "model",
    "service_tier",
    "provider_status",
    "input_tokens",
    "cached_input_tokens",
    "cache_write_tokens",
    "output_tokens",
    "reasoning_tokens",
    "total_tokens",
    "cost_micro_usd",
    "latency_ms",
    "error_code",
    "recorded_at",
}


class AIMeteringJournal:
    """Append-only emergency storage that never contains prompts or responses."""

    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()

    def pending_count(self) -> int:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path, flags)
            with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
                fcntl.flock(handle.fileno(), fcntl.LOCK_SH)
                return sum(1 for line in handle if line.strip())
        except FileNotFoundError:
            return 0

    def append(self, record: Mapping[str, Any]) -> None:
        unexpected = set(record) - ALLOWED_FIELDS
        if unexpected:
            raise ValueError("AI metering journal contains unapproved fields")
        payload = {
            key: record[key]
            for key in sorted(record)
            if key in ALLOWED_FIELDS and record[key] is not None
        }
        payload.setdefault("recorded_at", datetime.now(timezone.utc).isoformat())
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        descriptor = os.open(
            self.path,
            os.O_APPEND
            | os.O_CREAT
            | os.O_WRONLY
            | getattr(os, "O_NOFOLLOW", 0),
            0o600,
        )
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            handle.write(
                json.dumps(payload, sort_keys=True, separators=(",", ":"))
                + "\n"
            )
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    def reconcile(
        self,
        callback: Callable[[Mapping[str, Any]], Any],
    ) -> int:
        """Apply every record and truncate only after all callbacks succeed."""
        flags = os.O_RDWR | getattr(os, "O_NOFOLLOW", 0)
        try:
            descriptor = os.open(self.path, flags)
        except FileNotFoundError:
            return 0
        with os.fdopen(descriptor, "r+", encoding="utf-8") as handle:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
            records = []
            for line in handle:
                if not line.strip():
                    continue
                value = json.loads(line)
                if not isinstance(value, dict) or set(value) - ALLOWED_FIELDS:
                    raise ValueError("AI metering journal record is invalid")
                records.append(value)
            for record in records:
                callback(record)
            handle.seek(0)
            handle.truncate(0)
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            return len(records)
