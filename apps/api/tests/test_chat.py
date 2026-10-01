import asyncio
import json
import socket
import threading
import time
from pathlib import Path

import httpx
import pytest
import uvicorn
from fastapi.testclient import TestClient

from agent_lab_api.contracts import EVENT_ADAPTER, Scenario
from agent_lab_api.conversation_models import ApiModels
from agent_lab_api.main import app, get_provider


def parsed(text: str) -> list[dict]:
    return [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]


def test_normal_contract_and_health():
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok", "mode": "offline"}
        response = client.post("/chat", json={"message": "你好🙂\n第二行"})
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    events = parsed(response.text)
    assert [event["type"] for event in events] == ["delta", "delta", "delta", "done"]
    assert [event["sequence"] for event in events] == list(range(4))
    assert len({event["request_id"] for event in events}) == 1
    assert "你好🙂\n第二行" in "".join(event.get("text", "") for event in events)
    for event in events:
        EVENT_ADAPTER.validate_python(event)


@pytest.mark.parametrize("message", ["", "  ", "x" * 2001])
def test_invalid_message_is_not_streamed(message):
    with TestClient(app) as client:
        assert client.post("/chat", json={"message": message}).status_code == 422


def test_unknown_scenario_and_extra_fields_rejected():
    with TestClient(app) as client:
        assert client.post("/chat", json={"message": "hi", "scenario": "live"}).status_code == 422
        assert (
            client.post("/chat", json={"message": "hi", "provider": "cloudflare"}).status_code
            == 422
        )


def test_offline_mode_cannot_bypass_persistence_ownership(monkeypatch):
    monkeypatch.delenv("AGENT_LAB_PERSISTENCE", raising=False)
    with TestClient(app) as client:
        response = client.get("/conversations")
        assert response.status_code == 503
        assert response.json()["detail"]["code"] == "persistence_disabled"
        assert client.get("/health").status_code == 200


@pytest.mark.parametrize(
    ("scenario", "code", "retryable"),
    [
        ("rate_limit", "rate_limited", True),
        ("quota", "quota_exhausted", False),
        ("timeout", "provider_timeout", True),
        ("dependency_failure", "dependency_failure", True),
    ],
)
def test_failure_terminal_is_distinct_and_never_done(scenario, code, retryable):
    with TestClient(app) as client:
        response = client.post("/chat", json={"message": "hello", "scenario": scenario})
    events = parsed(response.text)
    assert len(events) == 1
    assert events[0]["type"] == "error"
    assert events[0]["code"] == code
    assert events[0]["retryable"] is retryable


def test_internal_diagnostics_are_not_returned():
    class FailingProvider:
        async def stream(self, message: str, scenario: Scenario):
            yield "第一段"
            raise RuntimeError("INTERNAL_DIAGNOSTIC")

    app.dependency_overrides[get_provider] = FailingProvider
    try:
        with TestClient(app) as client:
            response = client.post("/chat", json={"message": "hello"})
        assert "INTERNAL_DIAGNOSTIC" not in response.text
        assert [item["type"] for item in parsed(response.text)] == ["delta", "error"]
        assert parsed(response.text)[-1]["code"] == "provider_failure"
    finally:
        app.dependency_overrides.clear()


def test_exported_contracts_are_current():
    root = Path(__file__).resolve().parents[3]
    expected = EVENT_ADAPTER.json_schema()
    expected["title"] = "ChatEvent"
    assert json.loads((root / "contracts/chat-event.schema.json").read_text()) == expected
    assert json.loads((root / "contracts/openapi.json").read_text()) == app.openapi()
    assert (
        json.loads((root / "contracts/conversation.schema.json").read_text())
        == ApiModels.model_json_schema()
    )


@pytest.fixture
def server():
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    service = uvicorn.Server(uvicorn.Config(app, log_level="error", lifespan="off"))
    thread = threading.Thread(target=service.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not service.started:
        if not thread.is_alive() or time.monotonic() > deadline:
            service.should_exit = True
            raise RuntimeError("Local test server failed to start")
        time.sleep(0.01)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        service.should_exit = True
        thread.join(timeout=5)
        sock.close()
        assert not thread.is_alive()


async def test_first_event_under_one_second(server):
    async with httpx.AsyncClient(base_url=server) as client:
        start = time.monotonic()
        async with client.stream("POST", "/chat", json={"message": "first"}) as response:
            async for line in response.aiter_lines():
                if line.startswith("data: "):
                    assert time.monotonic() - start < 1
                    assert json.loads(line[6:])["type"] == "delta"
                    break


async def test_disconnect_closes_provider_without_more_chunks(server):
    closed = threading.Event()
    emitted = []

    class TracedProvider:
        async def stream(self, message: str, scenario: Scenario):
            try:
                emitted.append("first")
                yield "第一段"
                await asyncio.sleep(10)
                emitted.append("second")
                yield "不應送出"
            finally:
                closed.set()

    app.dependency_overrides[get_provider] = TracedProvider
    try:
        async with httpx.AsyncClient(base_url=server) as client:
            async with client.stream("POST", "/chat", json={"message": "cancel"}) as response:
                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        break
        assert await asyncio.to_thread(closed.wait, 2)
        assert emitted == ["first"]
    finally:
        app.dependency_overrides.clear()
