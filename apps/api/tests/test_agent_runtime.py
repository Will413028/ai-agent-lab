import asyncio
import json
import time
from contextlib import aclosing
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from agent_lab_api.agent_runtime import AgentRuntime
from agent_lab_api.artifacts import ArtifactStore, ToolFailure
from agent_lab_api.providers import ProviderFailure
from agent_lab_api.run_models import Run, Usage
from agent_lab_api.tools import ToolRegistry


def run(registry, **options):
    return Run(
        id=uuid4(),
        conversation_id=uuid4(),
        turn_id=uuid4(),
        workspace_id=registry.store.create(),
        goal="學習",
        status="running",
        max_steps=options.get("max_steps", 3),
        max_calls=options.get("max_calls", 4),
        answer="",
        error_code=None,
        created_at=datetime.now(UTC),
        finished_at=None,
    )


def call(name="searchWeb", arguments=None, id="call_1"):
    return {
        "role": "assistant",
        "tool_calls": [
            {
                "id": id,
                "type": "function",
                "function": {"name": name, "arguments": json.dumps(arguments or {"query": "學習"})},
            }
        ],
    }


class Script:
    mode = "fake"

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    async def decision(self, messages, tools):
        self.calls.append(json.loads(json.dumps(messages)))
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        if callable(reply):
            reply = await reply()
        return reply, Usage()


@pytest.fixture
def registry(tmp_path):
    return ToolRegistry(ArtifactStore(tmp_path / "workspaces"))


async def collect(runtime, item, cancel=None):
    persisted = []

    async def save(event):
        persisted.append(event.model_dump(mode="json"))

    async with aclosing(runtime.events(item, cancel or asyncio.Event(), save)) as events:
        seen = [event async for event in events]
    assert [e.sequence for e in seen] == list(range(len(seen)))
    assert [e.model_dump(mode="json") for e in seen] == persisted
    return seen


async def test_no_tools_completes_once_and_last_step_success(registry):
    model = Script({"role": "assistant", "content": "完成"})
    events = await collect(AgentRuntime(model, registry), run(registry, max_steps=1))
    assert events[-1].data.status == "succeeded"
    assert len(model.calls) == 1


async def test_unneeded_images_do_not_start_or_block_mcp(registry):
    class UnavailableImages:
        async def discover(self):
            raise AssertionError("discovery must be on demand")

        async def search(self, query):
            raise ToolFailure("dependency_failure", "圖片來源無法使用。")

    registry.add_images(UnavailableImages())
    model = Script({"role": "assistant", "content": "完成"})
    events = await collect(AgentRuntime(model, registry), run(registry))
    assert events[-1].data.status == "succeeded" and len(model.calls) == 1
    events = await collect(AgentRuntime(Script(call("searchImages")), registry), run(registry))
    assert events[-1].data.status == "failed" and events[-1].data.code == "dependency_failure"


async def test_provider_usage_is_summed_without_estimate_or_reasoning(registry):
    class Measured(Script):
        async def decision(self, messages, tools):
            message, _ = await super().decision(messages, tools)
            return message, Usage(source="provider", input_tokens=10, output_tokens=4)

    events = await collect(
        AgentRuntime(Measured(call(), {"role": "assistant", "content": "完成"}), registry),
        run(registry),
    )
    assert events[-1].data.usage == Usage(source="provider", input_tokens=20, output_tokens=8)


async def test_tools_preserve_call_ids_and_final_last_step(registry):
    model = Script(call(), {"role": "assistant", "content": "完成"})
    events = await collect(AgentRuntime(model, registry), run(registry, max_steps=2))
    assert events[-1].data.status == "succeeded"
    assert model.calls[1][-1]["role"] == "tool"
    assert model.calls[1][-1]["tool_call_id"] == "call_1"
    assert model.calls[1][-2]["tool_calls"][0]["id"] == "call_1"


async def test_step_limit_stops_more_model_calls(registry):
    model = Script(call())
    events = await collect(AgentRuntime(model, registry), run(registry, max_steps=1))
    assert events[-1].data.status == "limit" and events[-1].data.code == "step_limit"
    assert len(model.calls) == 1


async def test_call_limit_rejects_whole_batch_before_effects(registry):
    raw = call()
    raw["tool_calls"].append(call(id="call_2")["tool_calls"][0])
    model = Script(raw)
    events = await collect(AgentRuntime(model, registry), run(registry, max_calls=1))
    assert events[-1].data.code == "call_limit"
    assert not any(e.data.type == "tool_result" for e in events)


async def test_side_effect_occurs_once_even_when_tool_returns_failure(registry):
    executions = 0

    async def faulty(args, workspace_id):
        nonlocal executions
        executions += 1
        registry.store.put(workspace_id, "once.txt", b"saved", "text/plain")
        raise ToolFailure("tool_failure", "寫入後失敗")

    registry.register("faulty", "test", registry.tools["writeFile"].arguments, faulty, True)
    model = Script(call("faulty", {"fileName": "once.txt", "content": "x"}))
    item = run(registry)
    events = await collect(AgentRuntime(model, registry), item)
    assert events[-1].data.status == "failed"
    assert executions == 1 and len(model.calls) == 1
    assert len(registry.store.list(item.workspace_id)) == 1


async def test_cancel_stops_new_calls_within_deadline(registry):
    entered = asyncio.Event()
    cancel = asyncio.Event()

    async def blocked():
        entered.set()
        await asyncio.Event().wait()

    model = Script(blocked, call())
    task = asyncio.create_task(collect(AgentRuntime(model, registry), run(registry), cancel))
    await entered.wait()
    before = time.monotonic()
    cancel.set()
    events = await asyncio.wait_for(task, 2)
    assert time.monotonic() - before <= 2
    assert events[-1].data.status == "cancelled" and len(model.calls) == 1
    assert not any(e.data.type == "tool_call" for e in events)


async def test_cancel_between_tool_calls_never_starts_second(registry):
    cancel = asyncio.Event()
    model = Script(call())
    saved = []

    async def persist(event):
        saved.append(event)
        if event.data.type == "tool_call":
            cancel.set()

    async with aclosing(
        AgentRuntime(model, registry).events(run(registry), cancel, persist)
    ) as events:
        seen = [event async for event in events]
    assert seen[-1].data.status == "cancelled"
    assert not any(e.data.type == "tool_result" for e in seen)


async def test_timeout_and_model_failure_are_not_success(registry):
    async def blocked():
        await asyncio.Event().wait()

    events = await collect(AgentRuntime(Script(blocked), registry, deadline=0.05), run(registry))
    assert events[-1].data.code == "run_timeout"
    events = await collect(
        AgentRuntime(Script(ProviderFailure("provider_failure", "失敗", False)), registry),
        run(registry),
    )
    assert events[-1].data.status == "failed"


async def test_reasoning_never_reaches_events_logs_or_next_model_context(registry, caplog):
    first = call()
    first["reasoning"] = "REASONING_SENTINEL"
    model = Script(
        first, {"role": "assistant", "content": "完成", "reasoning_content": "REASONING_SENTINEL"}
    )
    events = await collect(AgentRuntime(model, registry), run(registry))
    assert "REASONING_SENTINEL" not in json.dumps([e.model_dump(mode="json") for e in events])
    assert "REASONING_SENTINEL" not in json.dumps(model.calls)
    assert "REASONING_SENTINEL" not in caplog.text
    assert events[-1].data.usage.source == "unknown"


async def test_disconnect_persists_cancel_and_releases_resources(registry):
    saved = []

    async def persist(event):
        saved.append(event)

    model = Script({"role": "assistant", "content": "unused"})
    started = time.monotonic()
    async with aclosing(
        AgentRuntime(model, registry).events(run(registry), asyncio.Event(), persist)
    ) as events:
        assert (await anext(events)).data.type == "started"
        assert time.monotonic() - started < 1
    assert saved[-1].data.status == "cancelled"
    assert len(model.calls) == 0


async def test_concurrent_runs_have_independent_workspace_and_history(registry):
    a, b = run(registry), run(registry)
    ma, mb = (
        Script({"role": "assistant", "content": "A"}),
        Script({"role": "assistant", "content": "B"}),
    )
    ea, eb = await asyncio.gather(
        collect(AgentRuntime(ma, registry), a), collect(AgentRuntime(mb, registry), b)
    )
    assert a.workspace_id != b.workspace_id
    assert all(e.run_id == a.id for e in ea) and all(e.run_id == b.id for e in eb)
    assert ea[-1].data.answer == "A" and eb[-1].data.answer == "B"
