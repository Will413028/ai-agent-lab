import hashlib
import os
import re
from pathlib import Path

import psycopg


def connection_info() -> str:
    port = int(os.environ.get("AGENT_LAB_DB_PORT", "18762"))
    name = os.environ.get("AGENT_LAB_DB_NAME", "lab")
    if not 1024 <= port <= 65535 or not re.fullmatch(r"lab(?:_test_[a-z0-9]+)?", name):
        raise ValueError("Only project-local databases are supported")
    return f"host=127.0.0.1 port={port} dbname={name} user=lab connect_timeout=3"


def migrate() -> None:
    with psycopg.connect(connection_info(), options="-c statement_timeout=60000") as connection:
        connection.execute("SELECT pg_advisory_xact_lock(hashtext('agent_lab.migrations'))")
        connection.execute("CREATE SCHEMA IF NOT EXISTS agent_lab")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS agent_lab.migrations "
            "(version text PRIMARY KEY, checksum text NOT NULL)"
        )
        for path in sorted((Path(__file__).resolve().parents[1] / "migrations").glob("*.sql")):
            sql = path.read_text()
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            row = connection.execute(
                "SELECT checksum FROM agent_lab.migrations WHERE version=%s", (path.name,)
            ).fetchone()
            if row:
                if row[0] != checksum:
                    raise RuntimeError("Applied migration changed; add a new migration instead")
                continue
            connection.execute(sql, prepare=False)
            connection.execute(
                "INSERT INTO agent_lab.migrations VALUES (%s,%s)", (path.name, checksum)
            )


if __name__ == "__main__":
    migrate()
    print("Project-local migrations applied.")
