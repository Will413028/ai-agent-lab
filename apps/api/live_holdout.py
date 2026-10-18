"""Opt-in frozen functional holdout using an owned test DB and temporary live API."""

import argparse
import asyncio
import hashlib
import json
import os
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from agent_lab_api.conversation_models import LoveReport
from agent_lab_api.image_models import ImageSearchResult
from agent_lab_api.personal_config import load_personal_config
from agent_lab_api.run_models import RunEvent
from check_chat import available_port

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "docs/plans/2026-10-01-rebuild/holdout.json"


async def run(base_url):
    corpus = json.loads(CORPUS.read_text())
    attempt_id = "live-holdout-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
    evidence_dir = ROOT / "artifacts" / attempt_id
    evidence_dir.mkdir()
    rows, created = [], []
    stopped = False
    async with httpx.AsyncClient(base_url=base_url, trust_env=False, timeout=180) as client:
        config = (await client.get("/runtime/config")).json()
        if config != {
            "provider": "cloudflare",
            "tools_mode": "live",
            "images_mode": "live",
            "persistence_scope": "test",
        }:
            print(
                "Live holdout 未執行：需要專屬test DB與Cloudflare／live工具。拒絕fixture或dev DB。"
            )
            return 3

        async def request(path, **options):
            nonlocal stopped
            response = await client.request(options.pop("method", "GET"), path, **options)
            if response.status_code == 429:
                stopped = True
            if not response.is_success:
                try:
                    if response.json().get("detail", {}).get("code") in (
                        "rate_limited",
                        "quota_exhausted",
                    ):
                        stopped = True
                except (ValueError, AttributeError):
                    pass
            response.raise_for_status()
            return response

        async def chat(case):
            response = await request(
                "/conversations", method="POST", json={"title": "Live holdout " + case["id"]}
            )
            id = response.json()["id"]
            created.append(id)
            return id

        def chat_answer(response):
            nonlocal stopped
            events = [
                json.loads(line[6:])
                for line in response.text.splitlines()
                if line.startswith("data: ")
            ]
            if events and events[-1].get("code") in ("rate_limited", "quota_exhausted"):
                stopped = True
            if not events or events[-1].get("type") != "done":
                raise ValueError("chat_not_completed")
            return "".join(event.get("text", "") for event in events), events[-1]

        for case in corpus["cases"]:
            row = {
                "case": case["id"],
                "checked_at": datetime.now(UTC).isoformat(),
                "status": "not_run",
                "rubric": case["rubric"],
            }
            before = time.monotonic()
            try:
                if stopped:
                    row["failure_class"] = "quota_stop"
                elif case["kind"] == "images":
                    result = ImageSearchResult.model_validate(
                        (
                            await request(
                                "/mcp/images/search", method="POST", json={"query": case["query"]}
                            )
                        ).json()
                    )
                    assert result.provider == "Wikimedia Commons" and result.images
                    assert all(
                        image.artist and image.license and image.license_url
                        for image in result.images
                    )
                    row.update(
                        status="passed",
                        image_count=len(result.images),
                        allowed_images=result.model_dump(mode="json"),
                    )
                else:
                    id = await chat(case)
                    if case["kind"] == "chat":
                        answers = []
                        for question in case["messages"]:
                            response = await request(
                                f"/conversations/{id}/chat",
                                method="POST",
                                json={"message": question},
                            )
                            answer, _ = chat_answer(response)
                            answers.append(answer)
                        row.update(status="needs_review", allowed_answers=answers)
                    elif case["kind"] == "report":
                        await request(
                            f"/conversations/{id}/reply",
                            method="POST",
                            json={"message": case["message"]},
                        )
                        result = (
                            await request(f"/conversations/{id}/reports", method="POST")
                        ).json()
                        report = LoveReport.model_validate(result["content"])
                        row.update(status="needs_review", allowed_report=report.model_dump())
                    elif case["kind"] == "rag":
                        document = await request(
                            "/documents",
                            method="POST",
                            files={
                                "file": (
                                    "holdout-source.md",
                                    case["document"].encode(),
                                    "text/markdown",
                                )
                            },
                            data={"relationship_status": "general"},
                        )
                        document_id = document.json()["id"]
                        try:
                            answers = []
                            for question in case["questions"]:
                                response = await request(
                                    f"/conversations/{id}/rag",
                                    method="POST",
                                    json={"message": question, "threshold": 0.0, "top_k": 3},
                                )
                                answer, _ = chat_answer(response)
                                answers.append(answer)
                            retrievals = (await request(f"/conversations/{id}/retrievals")).json()
                            row["retrieval_snapshots"] = retrievals
                            assert any(
                                c["document_id"] == document_id
                                for r in retrievals
                                for c in r["citations"]
                            )
                            row.update(
                                status="needs_review",
                                allowed_answers=answers,
                                source=case["document"],
                                retrieval_snapshots=retrievals,
                            )
                        finally:
                            await request(f"/documents/{document_id}", method="DELETE")
                    else:
                        response = await request(
                            f"/conversations/{id}/runs/stream",
                            method="POST",
                            json={"goal": case["goal"], "max_steps": 6, "max_calls": 12},
                        )
                        events = [
                            RunEvent.model_validate_json(line[6:])
                            for line in response.text.splitlines()
                            if line.startswith("data: ")
                        ]
                        row["allowed_run_events"] = [e.model_dump(mode="json") for e in events]
                        assert [e.sequence for e in events] == list(range(len(events)))
                        assert (
                            len({e.run_id for e in events}) == 1
                            and events[0].data.type == "started"
                        )
                        assert events and events[-1].data.type == "done"
                        final = events[-1].data
                        if final.code in ("rate_limited", "quota_exhausted"):
                            stopped = True
                        assert final.status == "succeeded"
                        calls = [e.data.call.name for e in events if e.data.type == "tool_call"]
                        if case["kind"] == "no_tools":
                            assert not calls and final.answer.strip()
                            row.update(status="passed", allowed_answer=final.answer)
                        else:
                            assert "searchWeb" in calls and "generatePDF" in calls
                            assert calls.index("searchWeb") < calls.index("generatePDF")
                            assert all(
                                e.data.result.status == "success"
                                for e in events
                                if e.data.type == "tool_result"
                            )
                            workspace = events[0].data.workspace_id
                            artifacts = (await request(f"/workspaces/{workspace}/artifacts")).json()
                            pdf = next(
                                a
                                for a in artifacts
                                if a["media_type"] == "application/pdf" and a["size"] > 0
                            )
                            content = (
                                await request(f"/workspaces/{workspace}/artifacts/{pdf['id']}")
                            ).content
                            assert content.startswith(b"%PDF-")
                            (evidence_dir / "H04.pdf").write_bytes(content)
                            row.update(
                                status="needs_review",
                                tool_names=calls,
                                artifact_bytes=len(content),
                                allowed_answer=final.answer,
                                allowed_run_events=[e.model_dump(mode="json") for e in events],
                                artifact_file="H04.pdf",
                                artifact_sha256=hashlib.sha256(content).hexdigest(),
                            )
                        row["provider_usage"] = final.usage.model_dump()
            except Exception:
                row.update(status="failed", failure_class="functional_check_failed")
            row["duration_ms"] = round((time.monotonic() - before) * 1000)
            rows.append(row)
            print(case["id"], row["status"], flush=True)
        output = {
            "attempt_id": attempt_id,
            "corpus_sha256": hashlib.sha256(CORPUS.read_bytes()).hexdigest(),
            "thinking": os.environ.get("AGENT_LAB_THINKING", "on"),
            "cases": rows,
            "note": "needs_review 必須依 rubric 逐例判讀；單次通過不代表品質或可靠率。",
        }
        path = evidence_dir / "attempt.json"
        with path.open("x") as file:
            json.dump(output, file, ensure_ascii=False, indent=2)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        # Persist all review evidence before deleting its source rows.
        cleanup = []
        for id in created:
            try:
                await request(f"/conversations/{id}", method="DELETE")
                cleanup.append(True)
            except Exception:
                cleanup.append(False)
    with (evidence_dir / "cleanup.json").open("x") as file:
        json.dump({"attempt_id": attempt_id, "owned_conversation_cleanup": cleanup}, file)
        file.write("\n")
    return 0 if all(row["status"] == "passed" for row in rows) else 1


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--own-server", action="store_true", required=True)
    parser.parse_args()
    if not os.environ.get("AGENT_LAB_DB_NAME", "").startswith("lab_test_"):
        raise RuntimeError("Disposable database required")
    load_personal_config(ROOT / ".env")
    port = available_port()
    env = {
        **os.environ,
        "AGENT_LAB_PROVIDER": "cloudflare",
        "AGENT_LAB_TOOLS": "live",
        "AGENT_LAB_IMAGES": "live",
        "AGENT_LAB_PERSISTENCE": "1",
    }
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "uvicorn",
        "agent_lab_api.main:app",
        "--app-dir",
        str(ROOT / "apps/api"),
        "--host",
        "127.0.0.1",
        "--port",
        port,
        env=env,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    base_url = "http://127.0.0.1:" + port
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=2) as ready:
            deadline = time.monotonic() + 30
            while True:
                if process.returncode is not None or time.monotonic() > deadline:
                    raise RuntimeError("Owned live API did not start")
                try:
                    if (await ready.get(base_url + "/health")).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                await asyncio.sleep(0.1)
        return await run(base_url)
    finally:
        if process.returncode is None:
            process.terminate()
            try:
                await asyncio.wait_for(process.wait(), 5)
            except TimeoutError:
                process.kill()
                await process.wait()


if __name__ == "__main__":
    try:
        code = asyncio.run(main())
    except Exception:
        print("Live holdout 未完成：服務尚未就緒；未輸出診斷或 credential。")
        code = 3
    raise SystemExit(code)
