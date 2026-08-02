from __future__ import annotations

import uuid
from contextlib import contextmanager

import psycopg


def db_connection(database_url: str, *, autocommit: bool = True) -> psycopg.Connection:
    """Open a bounded test connection that cannot wait forever on PostgreSQL."""
    return psycopg.connect(
        database_url,
        autocommit=autocommit,
        options="-c lock_timeout=5s -c statement_timeout=10s",
    )


pending_user_cleanup: set[uuid.UUID] = set()


@contextmanager
def isolated_test_users(*user_ids: uuid.UUID):
    """Queue users for cleanup after the API pool has been drained."""
    try:
        yield
    finally:
        pending_user_cleanup.update(user_ids)
