"""Small runtime configuration helpers for optional Mirror behavior."""

from __future__ import annotations

import os
from typing import Mapping


def mirror_voice_output_enabled(values: Mapping[str, str] | None = None) -> bool:
    """Return the strict, default-off Mirror speech-output gate."""
    source = values if values is not None else os.environ
    value = str(source.get("MIRROR_VOICE_OUTPUT_ENABLED", "false")).strip().lower()
    if value in {"1", "true", "yes", "on"}:
        return True
    if value in {"0", "false", "no", "off", ""}:
        return False
    raise ValueError("MIRROR_VOICE_OUTPUT_ENABLED must be true or false")
