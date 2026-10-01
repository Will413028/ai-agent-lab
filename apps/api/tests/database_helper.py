import asyncio
import os
import subprocess
import time
from pathlib import Path

import psycopg


async def restart_database(repository):
    if native := os.environ.get("AGENT_LAB_TEST_NATIVE_DIR"):
        restart = [
            os.environ["AGENT_LAB_TEST_PG_CTL"],
            "-D",
            native,
            "-l",
            str(Path(native).parent / "server.log"),
            "-m",
            "fast",
            "-w",
            "restart",
        ]
    else:
        restart = ["docker", "restart", os.environ["AGENT_LAB_TEST_CONTAINER"]]
    await asyncio.to_thread(subprocess.run, restart, check=True, capture_output=True, timeout=60)
    deadline = time.monotonic() + 30
    while True:
        try:
            async with repository.connection() as db:
                await db.execute("SELECT 1")
            return
        except psycopg.Error:
            if time.monotonic() > deadline:
                raise
            await asyncio.sleep(0.2)
