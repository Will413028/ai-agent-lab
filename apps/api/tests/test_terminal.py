import asyncio
import shlex

import pytest

from agent_lab_api.artifacts import ArtifactStore, ToolFailure
from agent_lab_api.terminal import DockerTerminal, docker


@pytest.mark.integration
async def test_actual_container_nonroot_readonly_no_network_and_artifact_exchange(tmp_path):
    store = ArtifactStore(tmp_path / "workspaces")
    workspace = store.create()
    store.put(workspace, "input.txt", "中文輸入".encode(), "text/plain")
    source = """import os, pathlib, socket
assert os.getuid() == 65534
assert pathlib.Path("input.txt").read_text() == "中文輸入"
try:
    pathlib.Path("/sandbox-write-test").write_text("blocked")
except OSError:
    pass
else:
    raise AssertionError("root filesystem writable")
s = socket.socket(); s.settimeout(0.3)
try:
    s.connect(("1.1.1.1", 443))
except OSError:
    pass
else:
    raise AssertionError("network available")
finally:
    s.close()
pathlib.Path("output.txt").write_text("中文輸出")
print("nonroot readonly network-none passed")
"""
    command = "python -c " + shlex.quote(source)
    result = await DockerTerminal().execute(command, workspace, store)
    assert result["exit_code"] == 0 and "network-none passed" in result["output"]
    assert store.read_named(workspace, "output.txt") == "中文輸出"
    assert {item["name"] for item in result["artifacts"]} == {"input.txt", "output.txt"}


@pytest.mark.integration
async def test_terminal_failure_is_not_success_and_owned_container_removed(tmp_path):
    store = ArtifactStore(tmp_path / "workspaces")
    workspace = store.create()
    with pytest.raises(ToolFailure, match="terminal_failed"):
        await DockerTerminal().execute("exit 7", workspace, store)
    # Assert only the current repo's terminal resources; no global cleanup.
    names = await docker(
        "ps", "-a", "--filter", "label=ai-agent-lab.owner=terminal", "--format", "{{.Names}}"
    )
    assert not names.strip()


@pytest.mark.integration
async def test_actual_terminal_cancel_cleans_its_owned_container(tmp_path, monkeypatch):
    import agent_lab_api.terminal as terminal

    store = ArtifactStore(tmp_path / "workspaces")
    original = terminal.docker_process
    owned = []
    started = asyncio.Event()

    async def observe(*args, **kwargs):
        if args[0] == "create":
            owned.append(args[args.index("--name") + 1])
        if kwargs.get("execution"):
            started.set()
        return await original(*args, **kwargs)

    monkeypatch.setattr(terminal, "docker_process", observe)
    task = asyncio.create_task(
        DockerTerminal().execute("printf ready > running.txt; sleep 60", store.create(), store)
    )
    try:
        await asyncio.wait_for(started.wait(), 90)
        # A workspace marker proves the actual command started before cancellation.
        async with asyncio.timeout(10):
            while True:
                _, code, _ = await original(
                    "exec",
                    owned[0],
                    "/bin/sh",
                    "-c",
                    "test -f /workspace/running.txt",
                    deadline=5,
                    execution=True,
                )
                if code == 0:
                    break
                await asyncio.sleep(0.1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        names = await docker("ps", "-a", "--filter", "name=" + owned[0], "--format", "{{.Names}}")
        assert owned[0] not in names.decode().splitlines()
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@pytest.mark.integration
async def test_actual_terminal_deadline_is_failure_and_cleanup(tmp_path):
    store = ArtifactStore(tmp_path / "workspaces")
    with pytest.raises(ToolFailure, match="tool_timeout"):
        await DockerTerminal().execute("sleep 60", store.create(), store)
    names = await docker(
        "ps", "-a", "--filter", "label=ai-agent-lab.owner=terminal", "--format", "{{.Names}}"
    )
    assert not names.strip()
