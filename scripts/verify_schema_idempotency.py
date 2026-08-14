"""Exercise schema.sql against disposable PostgreSQL databases in CI."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

import psycopg

REPO_ROOT = Path(__file__).resolve().parents[1]
CURRENT_SCHEMA = REPO_ROOT / "db" / "schema.sql"
EXPECTED_COUNTS = (157, 264, 6)
EXPECTED_ADMIN_VIEW_COLUMNS = (
    "content_id",
    "language",
    "content_type",
    "target_text",
    "translation",
    "status",
    "flag_count",
    "oldest_flag_at",
    "reasons",
    "reporter_count",
    "flags",
)


def apply_schema(database_url: str, schema: Path) -> None:
    with psycopg.connect(database_url, autocommit=True) as connection:
        connection.execute(schema.read_text(encoding="utf-8"))


def seed(database_url: str) -> None:
    environment = os.environ.copy()
    environment["DATABASE_URL"] = database_url
    subprocess.run(
        [sys.executable, str(REPO_ROOT / "db" / "seed" / "seed.py"), "--all"],
        cwd=REPO_ROOT,
        env=environment,
        check=True,
    )


def content_counts(database_url: str) -> tuple[int, int, int]:
    with (
        psycopg.connect(database_url) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT "
            "(SELECT count(*) FROM content_items), "
            "(SELECT count(*) FROM content_translations), "
            "(SELECT count(*) FROM tracks)"
        )
        row = cursor.fetchone()
    assert row is not None
    return tuple(row)  # type: ignore[return-value]


def check_fresh(database_url: str) -> None:
    apply_schema(database_url, CURRENT_SCHEMA)
    seed(database_url)
    first = content_counts(database_url)
    print(f"fresh pass 1 counts: items={first[0]}, translations={first[1]}, tracks={first[2]}")

    apply_schema(database_url, CURRENT_SCHEMA)
    seed(database_url)
    second = content_counts(database_url)
    print(f"fresh pass 2 counts: items={second[0]}, translations={second[1]}, tracks={second[2]}")

    if first != EXPECTED_COUNTS or second != EXPECTED_COUNTS or first != second:
        raise SystemExit(
            f"fresh idempotency failed: expected {EXPECTED_COUNTS}, got {first} then {second}"
        )
    print("fresh idempotency check passed")


def check_historical(database_url: str, historical_schema: Path) -> None:
    apply_schema(database_url, historical_schema)
    apply_schema(database_url, CURRENT_SCHEMA)

    with (
        psycopg.connect(database_url) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(
            "SELECT EXISTS ("
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'languages' "
            "AND column_name = 'required_validators')"
        )
        required_validators = cursor.fetchone()[0]
        cursor.execute("SELECT to_regclass('public.contributors') IS NOT NULL")
        contributors = cursor.fetchone()[0]
        cursor.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = 'admin_flag_queue' "
            "ORDER BY ordinal_position"
        )
        view_columns = tuple(row[0] for row in cursor.fetchall())

    if not required_validators:
        raise SystemExit("historical upgrade failed: languages.required_validators is absent")
    if not contributors:
        raise SystemExit("historical upgrade failed: contributors is absent")
    if view_columns != EXPECTED_ADMIN_VIEW_COLUMNS:
        raise SystemExit(
            "historical upgrade failed: admin_flag_queue columns are "
            f"{view_columns}, expected {EXPECTED_ADMIN_VIEW_COLUMNS}"
        )
    print("historical upgrade check passed")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    fresh = subparsers.add_parser("fresh")
    fresh.add_argument("--database-url", required=True)
    historical = subparsers.add_parser("historical")
    historical.add_argument("--database-url", required=True)
    historical.add_argument("--schema", required=True, type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "fresh":
        check_fresh(args.database_url)
    else:
        check_historical(args.database_url, args.schema)


if __name__ == "__main__":
    main()
