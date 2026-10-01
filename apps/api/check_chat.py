"""Own a disposable database for integration and browser checks, never use the dev volume."""

import argparse
import os
import socket
import subprocess
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[2]
IMAGE = "pgvector/pgvector:0.8.6-pg17-trixie"


def command(args: list[str], *, env=None, capture=False):
    return subprocess.run(args, check=True, env=env, text=True, capture_output=capture, timeout=600)


def available_port() -> str:
    with socket.socket() as reservation:
        reservation.bind(("127.0.0.1", 0))
        return str(reservation.getsockname()[1])


@contextmanager
def native_database(bindir: Path, database: str):
    artifacts = ROOT / "artifacts"
    artifacts.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="ai-agent-lab-test-", dir=artifacts) as folder:
        data = Path(folder) / "data"
        ctl = str(bindir / "pg_ctl")
        command(
            [
                str(bindir / "initdb"),
                "-D",
                str(data),
                "-U",
                "lab",
                "--auth=trust",
                "--encoding=UTF8",
                "--locale=C",
            ],
            capture=True,
        )
        port = available_port()
        started = False
        try:
            command(
                [
                    ctl,
                    "-D",
                    str(data),
                    "-l",
                    str(Path(folder) / "server.log"),
                    "-o",
                    f"-h 127.0.0.1 -p {port} -c unix_socket_directories=",
                    "-w",
                    "start",
                ],
                capture=True,
            )
            started = True
            with psycopg.connect(
                host="127.0.0.1",
                port=port,
                dbname="postgres",
                user="lab",
                autocommit=True,
                connect_timeout=3,
            ) as db:
                db.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
                print(f"Native validation: PostgreSQL {db.info.server_version}.", flush=True)
            yield {
                "AGENT_LAB_DB_PORT": port,
                "AGENT_LAB_TEST_NATIVE_DIR": str(data),
                "AGENT_LAB_TEST_PG_CTL": ctl,
            }
        finally:
            if started:
                command([ctl, "-D", str(data), "-m", "fast", "-w", "stop"], capture=True)


def run_checks(env, mutation, suite="chat"):
    command([sys.executable, "-m", "agent_lab_api.database"], env=env)
    if suite == "holdout":
        command([sys.executable, str(ROOT / "apps/api/live_holdout.py"), "--own-server"], env=env)
        return
    pytest = [
        sys.executable,
        "-m",
        "pytest",
        "-c",
        str(ROOT / "apps/api/pyproject.toml"),
        str(
            ROOT
            / "apps/api/tests"
            / {"rag": "test_rag.py", "agent": "test_runs.py", "chat": "test_conversations.py"}[
                suite
            ]
        ),
    ]
    command(pytest, env=env)
    if mutation and suite == "chat":
        path = ROOT / "apps/api/agent_lab_api/repository.py"
        original = path.read_text()
        needle = "SELECT * FROM agent_lab.turns WHERE conversation_id=%s "
        assert original.count(needle) == 1
        try:
            path.write_text(
                original.replace(needle, "SELECT * FROM agent_lab.turns WHERE %s IS NOT NULL ")
            )
            result = subprocess.run(
                [*pytest, "-k", "two_conversations_are_isolated"],
                env=env,
                text=True,
                capture_output=True,
            )
            assert result.returncode == 1 and "AssertionError" in result.stdout, result.stdout
            artifacts = ROOT / "artifacts"
            artifacts.mkdir(exist_ok=True)
            (artifacts / "s2-isolation-mutation.log").write_text(result.stdout + result.stderr)
            print("PASS: missing conversation filter fails the real database isolation test.")
        finally:
            path.write_text(original)
        command([*pytest, "-k", "two_conversations_are_isolated"], env=env)
    if mutation and suite == "rag":
        mutations = [
            (
                "knowledge.py",
                "WHERE (%s::text IS NULL OR d.relationship_status IN ('general',%s)) ",
                "WHERE (%s::text IS NULL OR %s::text IS NOT NULL) ",
                "status_filter",
            ),
            (
                "rag.py",
                "*messages[1:]",
                "*[m.model_copy(update={'content': result.retrieval_query}) "
                "if m.role == 'user' else m for m in messages[1:]]",
                "preserves_original",
            ),
        ]
        for filename, needle, replacement, test in mutations:
            path = ROOT / "apps/api/agent_lab_api" / filename
            original = path.read_text()
            assert original.count(needle) == 1
            try:
                path.write_text(original.replace(needle, replacement))
                result = subprocess.run(
                    [*pytest, "-k", test], env=env, text=True, capture_output=True
                )
                (ROOT / "artifacts" / f"s3-{test}-mutation.log").write_text(
                    result.stdout + result.stderr
                )
                assert result.returncode == 1 and "AssertionError" in result.stdout, result.stdout
                print(f"PASS: RAG mutation {test} fails its behavioral regression test.")
            finally:
                path.write_text(original)
            command([*pytest, "-k", test], env=env)
    browser = ["pnpm", "--dir", str(ROOT / "apps/web"), "exec", "playwright", "test"]
    if suite == "rag":
        browser.append("knowledge.spec.ts")
    if suite == "agent":
        browser.append("agent.spec.ts")
    command(browser, env=env)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mutation", action="store_true")
    parser.add_argument("--suite", choices=("chat", "rag", "agent", "holdout"), default="chat")
    parser.add_argument("--ready-timeout", type=int, default=120)
    parser.add_argument(
        "--postgres-bin",
        type=Path,
        help="Explicit native PostgreSQL bin directory; no automatic fallback",
    )
    args = parser.parse_args()
    if not 1 <= args.ready_timeout <= 1200:
        parser.error("--ready-timeout must be between 1 and 1200 seconds")
    suffix = uuid4().hex[:12]
    name = f"ai-agent-lab-test-{suffix}"
    database = f"lab_test_{suffix}"
    if args.postgres_bin:
        with native_database(args.postgres_bin.resolve(), database) as settings:
            env = os.environ.copy()
            env.pop("AGENT_LAB_TEST_CONTAINER", None)
            env.update(
                settings,
                AGENT_LAB_DB_NAME=database,
                AGENT_LAB_E2E_PERSISTENCE="1",
                PYTHONPATH=str(ROOT / "apps/api"),
            )
            run_checks(env, args.mutation, args.suite)
        return
    created = False
    planned_port = available_port()
    try:
        command(
            [
                "docker",
                "run",
                "-d",
                "--rm",
                "--name",
                name,
                "-e",
                "POSTGRES_HOST_AUTH_METHOD=trust",
                "-e",
                "POSTGRES_USER=lab",
                "-e",
                f"POSTGRES_DB={database}",
                "-p",
                f"127.0.0.1:{planned_port}:5432",
                IMAGE,
            ],
            capture=True,
        )
        created = True
        port = command(
            [
                "docker",
                "inspect",
                "--format",
                '{{(index (index .NetworkSettings.Ports "5432/tcp") 0).HostPort}}',
                name,
            ],
            capture=True,
        ).stdout.strip()
        assert port == planned_port, "Disposable database port did not match its explicit binding"
        env = os.environ.copy()
        env.pop("AGENT_LAB_TEST_NATIVE_DIR", None)
        env.pop("AGENT_LAB_TEST_PG_CTL", None)
        env.update(
            AGENT_LAB_DB_PORT=port,
            AGENT_LAB_DB_NAME=database,
            AGENT_LAB_TEST_CONTAINER=name,
            AGENT_LAB_E2E_PERSISTENCE="1",
            PYTHONPATH=str(ROOT / "apps/api"),
        )
        deadline = time.monotonic() + args.ready_timeout
        print(f"Waiting up to {args.ready_timeout}s for disposable PostgreSQL.", flush=True)
        while True:
            try:
                with psycopg.connect(
                    host="127.0.0.1", port=port, dbname=database, user="lab", connect_timeout=1
                ) as db:
                    assert db.execute("SELECT current_database()").fetchone()[0] == database
                break
            except psycopg.Error:
                if time.monotonic() > deadline:
                    raise RuntimeError("Disposable PostgreSQL did not become ready") from None
                time.sleep(0.5)
        run_checks(env, args.mutation, args.suite)
    finally:
        if created:
            # Only the random resource created by this check is stopped; --rm removes it.
            subprocess.run(["docker", "stop", name], check=False, capture_output=True)


if __name__ == "__main__":
    main()
