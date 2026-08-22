"""Fail-closed loader for reviewed AI prompt contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Union


class PromptContractError(RuntimeError):
    """Raised when a reviewed prompt contract cannot be loaded safely."""


def load_prompt_contract(path: Union[str, Path]) -> str:
    """Load a reviewed UTF-8 prompt, normalizing one trailing newline."""

    contract_path = Path(path)
    try:
        if contract_path.is_symlink() or not contract_path.is_file():
            raise PromptContractError("Prompt contract is not a regular file")
        reviewed = contract_path.read_text(encoding="utf-8")
    except PromptContractError:
        raise
    except (OSError, UnicodeError) as exc:
        raise PromptContractError("Prompt contract could not be loaded") from exc

    normalized = reviewed[:-1] if reviewed.endswith("\n") else reviewed
    if not normalized.strip():
        raise PromptContractError("Prompt contract is blank")
    return normalized
