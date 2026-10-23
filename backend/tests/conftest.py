"""Shared test fixtures. Tests use in-memory SQLite and recorded JSON; never the live API."""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app import models  # noqa: F401
from app.db import Base, get_db
from app.main import create_app

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def engine():
    eng = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _record):  # pragma: no cover - trivial
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def session_factory(engine):
    maker = sessionmaker(bind=engine, expire_on_commit=False)

    @contextmanager
    def scope() -> Iterator[Session]:
        s = maker()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    return scope


@pytest.fixture
def db(session_factory) -> Iterator[Session]:
    with session_factory() as s:
        yield s


@pytest.fixture
def api(session_factory) -> TestClient:
    app = create_app()

    def override() -> Iterator[Session]:
        with session_factory() as s:
            yield s

    app.dependency_overrides[get_db] = override
    return TestClient(app)


class FakeCF:
    """Stands in for CodeforcesClient with canned data."""

    def __init__(
        self,
        users: dict[str, dict[str, Any]] | None = None,
        submissions: dict[str, list[dict[str, Any]]] | None = None,
        ratings: dict[str, list[dict[str, Any]]] | None = None,
        problemset: dict[str, Any] | None = None,
    ) -> None:
        self.users = users or {}
        self.submissions = submissions or {}
        self.ratings = ratings or {}
        self.problemset = problemset or {"problems": [], "problemStatistics": []}
        self.calls: list[tuple[str, Any]] = []

    async def user_info(self, handles: list[str]) -> list[dict[str, Any]]:
        from app.cf.client import CFNotFound

        self.calls.append(("user.info", handles))
        out = []
        for h in handles:
            if h.lower() not in self.users:
                raise CFNotFound(f"handles: User with handle {h} not found")
            out.append(self.users[h.lower()])
        return out

    async def user_status(self, handle: str, from_: int, count: int) -> list[dict[str, Any]]:
        self.calls.append(("user.status", (handle, from_, count)))
        subs = self.submissions.get(handle.lower(), [])
        return subs[from_ - 1 : from_ - 1 + count]

    async def user_rating(self, handle: str) -> list[dict[str, Any]]:
        self.calls.append(("user.rating", handle))
        return self.ratings.get(handle.lower(), [])

    async def problemset_problems(self) -> dict[str, Any]:
        self.calls.append(("problemset.problems", None))
        return self.problemset
