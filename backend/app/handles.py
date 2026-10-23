"""Handle validation and normalisation."""

from __future__ import annotations

import re

from app.config import HANDLE_PATTERN

_HANDLE_RE = re.compile(HANDLE_PATTERN)


def is_valid_handle(handle: str) -> bool:
    """Letters, digits, underscore, dot, hyphen; 3 to 24 characters."""
    return bool(_HANDLE_RE.fullmatch(handle))


def handle_key(handle: str) -> str:
    """Case-insensitive storage key."""
    return handle.strip().lower()
