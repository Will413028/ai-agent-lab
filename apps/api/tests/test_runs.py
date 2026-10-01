import asyncio
import json
import time
from contextlib import aclosing
from uuid import UUID, uuid4

import pytest
from test_agent_runtime import Script, call
from test_conversations import client, isolated_database

from agent_lab_api.agent_runtime import AgentRuntime
from agent_lab_api.artifacts import ArtifactStore
from agent_lab_api.main import app, get_provider, get_run_model
from agent_lab_api.providers import FakeProvider
from agent_lab_api.repository import Busy, NotFound
from agent_lab_api.run_models import Final, RunEvent, RunRequest, Started
from agent_lab_api.run_repository import RunStore
from agent_lab_api.tools import ToolRegistry

__all__ = ["client", "isolated_database"]
pytestmark = pytest.mark.integration


async def test_run_and_turn_allocation_are_atomic_and_single_claim(isolated_database, tmp_path):
    repo = isolated_database
    chat = await repo.create("任務")
    store = RunStore(repo)
    request = RunRequest(goal="任務")
    results = await asyncio.gather(
        store.begin(chat.id, request, uuid4()),
        store.begin(chat.id, request, uuid4()),
        return_exceptions=True,
    )
    assert sum(isinstance(r, Busy) for r in results) == 1
    item = next(r for r in results if not isinstance(r, Exception))
    assert len((await repo.detail(chat.id)).turns) == 1
    await store.append(
        RunEvent(
            run_id=item.id,
            sequence=0,
            data=Started(workspace_id=item.workspace_id, provider="fake"),
        )
    )
    await store.append(
        RunEvent(run_id=item.id, sequence=1, data=Final(status="succeeded", answer="完成"))
    )
    assert (await repo.detail(chat.id)).turns[0].status == "completed"
    with pytest.raises(Busy):
        await store.append(
            RunEvent(run_id=item.id, sequence=2, data=Final(status="failed", answer="覆寫"))
        )


async def test_warm_no_tool_request_finishes_within_first_event_boundary(client):
    chat = (await client.post("/conversations", json={"title": "時間驗收"})).json()["id"]
    started = time.monotonic()
    response = await client.post(
        f"/conversations/{chat}/runs/stream", json={"goal": "fixture:no-tools"}
    )
    assert response.status_code == 200
    # ASGI buffers the complete response: completion <1s is stronger than first event <1s.
    assert time.monotonic() - started < 1
    assert '"status":"succeeded"' in response.text


async def test_completed_run_reload_is_scoped_and_reasoning_is_never_saved(client, caplog):
    a = UUID((await client.post("/conversations", json={"title": "A"})).json()["id"])
    b = UUID((await client.post("/conversations", json={"title": "B"})).json()["id"])
    raw = {"role": "assistant", "content": "完成", "reasoning": "DB_REASONING_SENTINEL"}
    app.dependency_overrides[get_run_model] = lambda: Script(raw)
    response = await client.post(
        f"/conversations/{a}/runs/stream", json={"goal": "任務", "max_steps": 1}
    )
    assert response.status_code == 200
    wire = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    run_id = wire[0]["run_id"]
    detail = (await client.get(f"/conversations/{a}/runs/{run_id}")).json()
    assert detail["status"] == "succeeded" and detail["events"] == wire
    assert "DB_REASONING_SENTINEL" not in response.text + json.dumps(detail) + caplog.text
    assert (await client.get(f"/conversations/{b}/runs/{run_id}")).status_code == 404
    assert (await client.get(f"/conversations/{b}/runs")).json() == []
    captured = []

    class Traced(FakeProvider):
        async def stream(self, messages, scenario):
            captured.extend(messages)
            async for text in super().stream(messages, scenario):
                yield text

    app.dependency_overrides[get_provider] = Traced
    await client.post(f"/conversations/{a}/chat", json={"message": "延續任務結果"})
    assert any(m.role == "assistant" and m.content == "完成" for m in captured)


async def test_disconnect_persists_cancel_and_allows_next_run(isolated_database, tmp_path):
    repo = isolated_database
    store = RunStore(repo)
    chat = await repo.create("取消")
    registry = ToolRegistry(ArtifactStore(tmp_path / "workspaces"))
    item = await store.begin(chat.id, RunRequest(goal="任務"), registry.store.create())
    runtime = AgentRuntime(Script({"role": "assistant", "content": "unused"}), registry)
    async with aclosing(runtime.events(item, asyncio.Event(), store.append)) as events:
        await anext(events)
    assert (await store.get(chat.id, item.id)).status == "cancelled"
    assert (await repo.detail(chat.id)).turns[0].status == "cancelled"
    await store.begin(chat.id, RunRequest(goal="下一輪"), registry.store.create())


async def test_startup_recovery_and_delete_cascade(isolated_database):
    repo = isolated_database
    store = RunStore(repo)
    chat = await repo.create("重啟")
    item = await store.begin(chat.id, RunRequest(goal="任務"), uuid4())
    with pytest.raises(Busy):
        await repo.delete(chat.id)
    await repo.recover_interrupted()
    await store.recover()
    assert (await store.get(chat.id, item.id)).error_code == "interrupted"
    await repo.delete(chat.id)
    with pytest.raises(NotFound):
        await store.get(chat.id, item.id)


async def test_two_parallel_runs_do_not_share_results(isolated_database, tmp_path):
    repo = isolated_database
    store = RunStore(repo)
    chats = [await repo.create("A"), await repo.create("B")]
    registry = ToolRegistry(ArtifactStore(tmp_path / "workspaces"))
    items = [
        await store.begin(chat.id, RunRequest(goal=chat.title), registry.store.create())
        for chat in chats
    ]

    async def execute(item):
        async with aclosing(
            AgentRuntime(
                Script(call(), {"role": "assistant", "content": item.goal}), registry
            ).events(item, asyncio.Event(), store.append)
        ) as events:
            return [event async for event in events]

    await asyncio.gather(*(execute(item) for item in items))
    rows = [await store.get(item.conversation_id, item.id) for item in items]
    assert [r.answer for r in rows] == ["A", "B"]
    assert all(all(e.run_id == row.id for e in row.events) for row in rows)
