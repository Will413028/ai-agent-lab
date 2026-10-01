import asyncio
import json
import os
from contextlib import aclosing
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from database_helper import restart_database

from agent_lab_api.context import SYSTEM_PROMPT
from agent_lab_api.database import migrate
from agent_lab_api.main import app, get_provider, lifespan
from agent_lab_api.providers import FakeProvider
from agent_lab_api.repository import Busy, Repository, StaleReport
from agent_lab_api.streaming import chat_events

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(autouse=True)
async def isolated_database():
    assert os.environ.get("AGENT_LAB_DB_NAME", "").startswith("lab_test_")
    if native := os.environ.get("AGENT_LAB_TEST_NATIVE_DIR"):
        data = await asyncio.to_thread(Path(native).resolve)
        assert data.parent.parent == ROOT / "artifacts"
        assert data.parent.name.startswith("ai-agent-lab-test-") and data.name == "data"
    else:
        assert os.environ.get("AGENT_LAB_TEST_CONTAINER", "").startswith("ai-agent-lab-test-")
    repository = Repository()
    yield repository
    app.dependency_overrides.clear()
    async with repository.connection() as db:
        await db.execute("TRUNCATE agent_lab.conversations CASCADE")


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_PERSISTENCE", "1")
    async with lifespan(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://local"
        ) as value:
            yield value


async def create(client, title="練習對話"):
    response = await client.post("/conversations", json={"title": title})
    assert response.status_code == 201
    return response.json()["id"]


async def send(client, conversation_id, message, scenario="normal"):
    response = await client.post(
        f"/conversations/{conversation_id}/chat", json={"message": message, "scenario": scenario}
    )
    assert response.status_code == 200
    return [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]


async def test_two_conversations_are_isolated(client):
    first = await create(client, "對話 A")
    second = await create(client, "對話 B")
    await send(client, first, "ALPHA_ONLY：我喜歡散步")
    events = await send(client, second, "BETA_ONLY：我喜歡電影")
    assert "ALPHA_ONLY" not in json.dumps(events, ensure_ascii=False)
    events = await send(client, first, "記得我的喜好嗎？")
    assert "ALPHA_ONLY" in json.dumps(events, ensure_ascii=False)
    assert "BETA_ONLY" not in json.dumps(events, ensure_ascii=False)
    a = (await client.get(f"/conversations/{first}")).json()
    b = (await client.get(f"/conversations/{second}")).json()
    assert len(a["turns"]) == 2 and len(b["turns"]) == 1
    assert all(t["conversation_id"] == first for t in a["turns"])
    assert all(t["conversation_id"] == second for t in b["turns"])


async def test_context_is_received_by_provider_and_failed_turn_is_excluded(client):
    prompts = []

    class Traced(FakeProvider):
        async def stream(self, messages, scenario):
            prompts.append(messages)
            async for text in super().stream(messages, scenario):
                yield text

    app.dependency_overrides[get_provider] = Traced
    conversation_id = await create(client)
    await send(client, conversation_id, "第一個問題")
    await send(client, conversation_id, "失敗問題", "quota")
    await send(client, conversation_id, "第三個問題")
    assert prompts[-1][0].content == SYSTEM_PROMPT
    assert [m.content for m in prompts[-1] if m.role == "user"] == ["第一個問題", "第三個問題"]
    assert [m.role for m in prompts[-1]] == ["system", "user", "assistant", "user"]
    detail = (await client.get(f"/conversations/{conversation_id}")).json()
    assert [t["status"] for t in detail["turns"]] == ["completed", "failed", "completed"]
    assert detail["turns"][1]["error_code"] == "quota_exhausted"


async def test_database_enforces_parallel_turn_claims_and_terminal_once(isolated_database):
    repo = isolated_database
    conversation = await repo.create("併行練習")
    results = await asyncio.gather(
        repo.begin(conversation.id, "A"), repo.begin(conversation.id, "B"), return_exceptions=True
    )
    assert sum(isinstance(result, Busy) for result in results) == 1
    turn, _history = next(result for result in results if not isinstance(result, Exception))
    await repo.finish(turn, "完成", "completed")
    with pytest.raises(Busy):
        await repo.finish(turn, "覆寫", "cancelled")
    assert (await repo.detail(conversation.id)).turns[0].answer == "完成"


async def test_busy_request_and_delete_are_rejected(client, isolated_database):
    repo = isolated_database
    conversation = await repo.create("正在回覆")
    turn, _ = await repo.begin(conversation.id, "A")
    assert (
        await client.post(f"/conversations/{conversation.id}/chat", json={"message": "B"})
    ).status_code == 409
    assert (await client.delete(f"/conversations/{conversation.id}")).status_code == 409
    assert (await client.post(f"/conversations/{conversation.id}/reports")).status_code == 409
    await repo.finish(turn, "", "cancelled")
    assert (await client.delete(f"/conversations/{conversation.id}")).status_code == 204


async def test_close_preserves_partial_and_releases_next_turn(isolated_database):
    repo = isolated_database
    conversation = await repo.create("取消練習")
    turn, _ = await repo.begin(conversation.id, "慢速")

    async def persist(answer, status, code):
        await repo.finish(turn, answer, status, code)

    from agent_lab_api.context import build_context

    async with aclosing(
        chat_events(FakeProvider(), build_context([], turn.question), "slow", persist)
    ) as events:
        first = await anext(events)
        assert first.type == "delta"
    detail = await repo.detail(conversation.id)
    assert detail.turns[0].status == "cancelled"
    assert detail.turns[0].answer == first.text
    new, _ = await repo.begin(conversation.id, "下一輪")
    await repo.finish(new, "完成", "completed")


async def test_synchronous_chat_uses_same_context_and_storage(client):
    conversation_id = await create(client)
    await send(client, conversation_id, "我想約對方散步")
    response = await client.post(
        f"/conversations/{conversation_id}/reply", json={"message": "我先前想做什麼？"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "completed"
    assert "我想約對方散步" in response.json()["answer"]


async def test_report_is_validated_stored_and_deleted_with_conversation(client, isolated_database):
    conversation_id = await create(client)
    await send(client, conversation_id, "如何溝通？")
    response = await client.post(f"/conversations/{conversation_id}/reports")
    assert response.status_code == 201
    assert response.json()["content"]["title"]
    assert 1 <= len(response.json()["content"]["suggestions"]) <= 5
    assert response.json()["source_position"] == 1
    assert (await client.get(f"/conversations/{conversation_id}/reports")).json() == [
        response.json()
    ]
    assert (await client.delete(f"/conversations/{conversation_id}")).status_code == 204
    assert (await client.get(f"/conversations/{conversation_id}")).status_code == 404
    async with isolated_database.connection() as db:
        for table in ["turns", "reports"]:
            cursor = await db.execute(
                f"SELECT count(*) AS n FROM agent_lab.{table} WHERE conversation_id=%s",
                (conversation_id,),
            )
            assert (await cursor.fetchone())["n"] == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"title": "valid", "suggestions": []},
        {"title": "valid", "suggestions": [""]},
        {"title": "valid", "suggestions": ["valid"], "secret_field": "not allowed"},
        "raw text",
    ],
)
async def test_invalid_provider_report_is_rejected_before_storage(client, payload):
    class BrokenReport(FakeProvider):
        async def report(self, messages):
            return payload

    app.dependency_overrides[get_provider] = BrokenReport
    conversation_id = await create(client)
    await send(client, conversation_id, "測試報告")
    response = await client.post(f"/conversations/{conversation_id}/reports")
    assert response.status_code == 502
    assert response.json()["detail"]["code"] == "invalid_report"
    assert (await client.get(f"/conversations/{conversation_id}/reports")).json() == []


async def test_report_snapshot_cannot_be_saved_after_new_turn(isolated_database):
    repo = isolated_database
    conversation = await repo.create("快照練習")
    first, _ = await repo.begin(conversation.id, "A")
    await repo.finish(first, "A", "completed")
    position, _ = await repo.report_source(conversation.id)
    second, _ = await repo.begin(conversation.id, "B")
    await repo.finish(second, "B", "completed")
    from agent_lab_api.conversation_models import LoveReport

    with pytest.raises(StaleReport):
        await repo.save_report(
            conversation.id, position, LoveReport(title="過期", suggestions=["舊內容"])
        )


async def test_api_singleton_lease_and_interrupted_recovery(isolated_database, monkeypatch):
    repo = isolated_database
    conversation = await repo.create("中斷")
    await repo.begin(conversation.id, "中斷問題")
    monkeypatch.setenv("AGENT_LAB_PERSISTENCE", "1")
    async with lifespan(app):
        detail = await repo.detail(conversation.id)
        assert detail.turns[0].status == "cancelled"
        assert detail.turns[0].error_code == "interrupted"
        with pytest.raises(RuntimeError, match="Only one"):
            from fastapi import FastAPI

            async with lifespan(FastAPI()):
                pytest.fail("A second API incorrectly acquired the singleton lease")


async def test_migration_idempotence_and_real_database_restart(isolated_database):
    from agent_lab_api.conversation_models import LoveReport

    repo = isolated_database
    conversation = await repo.create("持久化")
    turn, _ = await repo.begin(conversation.id, "重啟後還在")
    await repo.finish(turn, "完成", "completed")
    report = await repo.save_report(
        conversation.id, 1, LoveReport(title="報告", suggestions=["完成"])
    )
    await asyncio.to_thread(migrate)
    await restart_database(isolated_database)
    detail = await Repository().detail(conversation.id)
    assert detail.turns[0].question == "重啟後還在"
    assert detail.turns[0].status == "completed"
    assert (await Repository().reports(conversation.id))[0].id == report.id


async def test_empty_and_missing_conversation_reports_are_explicit(client):
    conversation_id = await create(client)
    assert (await client.post(f"/conversations/{conversation_id}/reports")).status_code == 409
    missing = uuid4()
    assert (await client.get(f"/conversations/{missing}")).status_code == 404
    assert (
        await client.post(f"/conversations/{missing}/chat", json={"message": "hi"})
    ).status_code == 404
