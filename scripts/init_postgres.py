from __future__ import annotations

import argparse
import asyncio
import os

from translume_clients.postgres import PostgresClientConfig, PostgresLedgerStore


async def _run(dsn: str) -> None:
    store = PostgresLedgerStore(PostgresClientConfig(dsn=dsn))
    await store.ensure_schema()


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize Translume Postgres tables.")
    parser.add_argument(
        "--dsn",
        default=os.getenv("POSTGRES_DSN", "postgresql://translume:translume@localhost:5432/translume"),
        help="Postgres DSN. Defaults to POSTGRES_DSN or local Docker Compose DSN.",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.dsn))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
