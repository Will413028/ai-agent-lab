import hashlib
import json

import httpx
import pytest

from agent_lab_api.cloudflare import CloudflareSettings
from agent_lab_api.providers import ProviderFailure
from live_spike import BudgetedProvider


async def test_live_budget_stops_sdk_calls_before_exceeding_limit():
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(
            200,
            json={
                "id": "test",
                "object": "chat.completion",
                "created": 0,
                "model": "test",
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "完成"},
                    }
                ],
            },
        )

    provider = BudgetedProvider(CloudflareSettings("0" * 32, "fixture-token"), limit=2)
    provider.transport = httpx.MockTransport(respond)
    for _ in range(2):
        await provider.completion([{"role": "user", "content": "test"}])
    with pytest.raises(ProviderFailure, match="request_budget"):
        await provider.completion([{"role": "user", "content": "extra"}])
    assert len(calls) == 2


async def test_quota_stops_subsequent_live_calls_without_retries(caplog):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(429, json={"error": {"message": "limited", "type": "rate_limit"}})

    provider = BudgetedProvider(CloudflareSettings("0" * 32, "fixture-token"))
    provider.transport = httpx.MockTransport(respond)
    with pytest.raises(ProviderFailure, match="rate_limited"):
        await provider.completion([{"role": "user", "content": "test"}])
    with pytest.raises(ProviderFailure, match="request_budget"):
        await provider.completion([{"role": "user", "content": "extra"}])
    assert len(calls) == 1 and "fixture-token" not in caplog.text


def test_holdout_is_separate_from_spike_and_covers_all_required_kinds():
    from live_holdout import CORPUS

    data = json.loads(CORPUS.read_text())
    assert {case["kind"] for case in data["cases"]} == {
        "chat",
        "report",
        "rag",
        "tools",
        "images",
        "no_tools",
    }
    assert len({case["id"] for case in data["cases"]}) == 8
    assert all(case["rubric"] for case in data["cases"])


def test_human_review_keeps_attempt_and_artifact_provenance_and_cannot_override_failure(tmp_path):
    from live_holdout import CORPUS
    from review_holdout import adjudicate

    corpus = CORPUS.read_bytes()
    content = b"%PDF-1.7 fixture"
    (tmp_path / "H04.pdf").write_bytes(content)
    rows = [{"case": case["id"], "status": "passed"} for case in json.loads(corpus)["cases"]]
    rows[3].update(
        status="needs_review",
        allowed_run_events=[{"summary": "search source"}],
        artifact_file="H04.pdf",
        artifact_sha256=hashlib.sha256(content).hexdigest(),
    )
    attempt = {
        "attempt_id": "test",
        "corpus_sha256": hashlib.sha256(corpus).hexdigest(),
        "cases": rows,
    }
    before = json.dumps(attempt)
    verdicts = {"H04": {"status": "passed", "reason": "已核對PDF內容與搜尋來源"}}
    result = adjudicate(attempt, verdicts, corpus, evidence_dir=tmp_path)
    assert result["conclusion"] == "passed" and json.dumps(attempt) == before
    (tmp_path / "H04.pdf").write_bytes(b"changed")
    with pytest.raises(ValueError, match="artifact_changed"):
        adjudicate(attempt, verdicts, corpus, evidence_dir=tmp_path)
    (tmp_path / "H04.pdf").write_bytes(content)
    rows[0]["status"] = "failed"
    assert (
        adjudicate(attempt, verdicts, corpus, evidence_dir=tmp_path)["conclusion"] == "incomplete"
    )
    with pytest.raises(ValueError, match="review_each_pending_case_only"):
        adjudicate(
            attempt,
            {**verdicts, "H01": {"status": "passed", "reason": "override"}},
            corpus,
            evidence_dir=tmp_path,
        )


def test_review_rejects_changed_corpus_and_missing_retrieval_evidence(tmp_path):
    from live_holdout import CORPUS
    from review_holdout import adjudicate

    corpus = CORPUS.read_bytes()
    rows = [{"case": case["id"], "status": "passed"} for case in json.loads(corpus)["cases"]]
    rows[2].update(status="needs_review", allowed_answers=["test"], source="test")
    attempt = {
        "attempt_id": "test",
        "corpus_sha256": hashlib.sha256(corpus).hexdigest(),
        "cases": rows,
    }
    verdicts = {"H03": {"status": "passed", "reason": "test"}}
    with pytest.raises(ValueError, match="missing_review_evidence"):
        adjudicate(attempt, verdicts, corpus, evidence_dir=tmp_path)
    with pytest.raises(ValueError, match="corpus_changed"):
        adjudicate(attempt, verdicts, corpus + b" ", evidence_dir=tmp_path)


async def test_holdout_persists_review_evidence_before_deleting_source_rows(tmp_path, monkeypatch):
    import live_holdout

    (tmp_path / "artifacts").mkdir()
    corpus = tmp_path / "corpus.json"
    corpus.write_text(
        json.dumps(
            {"cases": [{"id": "H01", "kind": "chat", "messages": ["人工測資"], "rubric": "test"}]}
        )
    )
    monkeypatch.setattr(live_holdout, "ROOT", tmp_path)
    monkeypatch.setattr(live_holdout, "CORPUS", corpus)
    deleted = []

    def respond(request):
        if request.url.path == "/runtime/config":
            return httpx.Response(
                200,
                json={
                    "provider": "cloudflare",
                    "tools_mode": "live",
                    "images_mode": "live",
                    "persistence_scope": "test",
                },
            )
        if request.method == "DELETE":
            attempts = list((tmp_path / "artifacts").glob("*/attempt.json"))
            assert len(attempts) == 1
            evidence = json.loads(attempts[0].read_text())
            assert evidence["cases"][0]["allowed_answers"] == ["回答"]
            deleted.append(request.url.path)
            return httpx.Response(204)
        if request.url.path == "/conversations":
            return httpx.Response(201, json={"id": "synthetic-conversation"})
        return httpx.Response(
            200, text='data: {"type":"delta","text":"回答"}\n\ndata: {"type":"done"}\n\n'
        )

    client = httpx.AsyncClient
    monkeypatch.setattr(
        live_holdout.httpx,
        "AsyncClient",
        lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(respond)),
    )
    assert await live_holdout.run("http://test.invalid") == 1
    assert deleted == ["/conversations/synthetic-conversation"]
    assert len(list((tmp_path / "artifacts").glob("*/cleanup.json"))) == 1
