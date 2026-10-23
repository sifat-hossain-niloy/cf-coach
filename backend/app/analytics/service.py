"""Glue between the DB and the pure analytics functions (filled in Phase 2)."""

from __future__ import annotations

from sqlalchemy.orm import Session


def refresh_analytics(db: Session, handle_id: int) -> None:
    """Recompute and cache every analytics payload for a handle."""
    return None
