from __future__ import annotations

import os
from contextlib import contextmanager
from functools import lru_cache
from typing import Any, Iterator


try:
    import psycopg
except Exception:  # pragma: no cover - optional dependency in some environments
    psycopg = None  # type: ignore[assignment]


def normalize_database_url(url: str) -> str:
    value = (url or "").strip()
    if value.startswith("postgresql+psycopg://"):
        return "postgresql://" + value[len("postgresql+psycopg://") :]
    return value


@lru_cache(maxsize=1)
def get_database_url() -> str:
    return normalize_database_url(os.environ.get("DATABASE_URL", ""))


def is_postgres_available() -> bool:
    return bool(psycopg is not None and get_database_url())


@contextmanager
def connection(autocommit: bool = False) -> Iterator[Any]:
    if psycopg is None:
        raise RuntimeError("psycopg is not installed")
    dsn = get_database_url()
    if not dsn:
        raise RuntimeError("DATABASE_URL is not configured")
    with psycopg.connect(dsn, autocommit=autocommit) as conn:
        yield conn
