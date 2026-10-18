"""Opt-in capability checks. Never save raw SDK responses, account identifiers or reasoning."""

import argparse
import asyncio
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import jsonschema

from agent_lab_api.agent_runtime import assistant_message
from agent_lab_api.cloudflare import (
    CHAT_MODEL,
    CONVERSATION_MODEL,
    EMBEDDING_MODEL,
    CloudflareEmbedder,
    CloudflareProvider,
    CloudflareSettings,
)
from agent_lab_api.conversation_models import PromptMessage
from agent_lab_api.personal_config import load_personal_config
from agent_lab_api.providers import ProviderFailure

ROOT = Path(__file__).resolve().parents[2]


class BudgetedProvider(CloudflareProvider):
    def __init__(self, settings, limit=10):
        super().__init__(settings)
        self.requests = 0
        self.limit = limit
        self.stopped = False

    def claim(self):
        if self.stopped or self.requests >= self.limit:
            raise ProviderFailure("request_budget", "Live request budget 已停止。", False)
        self.requests += 1

    async def completion_with_usage(self, messages, **options):
        self.claim()
        try:
            return await super().completion_with_usage(messages, **options)
        except ProviderFailure as failure:
            if failure.code == "rate_limited":
                self.stopped = True
            raise


async def spike(provider):
    rows = []
    simple = [{"role": "user", "content": "請用繁體中文說一句問候，限二十字。"}]
    schema = {
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "suggestions": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["title", "suggestions"],
        "additionalProperties": False,
    }
    definitions = [
        {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                    "additionalProperties": False,
                },
            },
        }
        for name, description in [
            ("lookup_city", "查詢城市資料"),
            ("format_plan", "依最新城市資料格式化計畫"),
        ]
    ]

    async def normal():
        message, usage = await provider.completion_with_usage(simple)
        assert message.get("content", "").strip()
        return {"response_shape": sorted(message), "provider_usage": usage.model_dump()}

    async def stream():
        provider.claim()
        pieces = []
        started = time.monotonic()
        first = None
        async for text in provider.stream(
            [PromptMessage(role="user", content=simple[0]["content"])], "normal"
        ):
            first = first or (time.monotonic() - started)
            pieces.append(text)
        assert "".join(pieces).strip()
        return {
            "response_shape": "content stream",
            "ttft_ms": round((first or 0) * 1000),
            "provider_usage": {"source": "unknown"},
        }

    async def structured():
        message, usage = await provider.completion_with_usage(
            [{"role": "user", "content": "回傳title與suggestions：一次室內約會計畫。"}],
            response_format={
                "type": "json_schema",
                "json_schema": {"name": "spike_report", "strict": True, "schema": schema},
            },
        )
        jsonschema.validate(json.loads(message["content"]), schema)
        return {"response_shape": "validated json_schema", "provider_usage": usage.model_dump()}

    async def tools(multi=False):
        messages = [
            {
                "role": "user",
                "content": "請先lookup_city查詢台北資料，再format_plan依資料格式化計畫，最後回答。"
                if multi
                else "請lookup_city查詢台北資料後回答。",
            }
        ]
        sequence = ["lookup_city", "format_plan"] if multi else ["lookup_city"]
        ids = []
        for name in sequence:
            raw, _ = await provider.completion_with_usage(
                messages, tools=definitions if multi else definitions[:1]
            )
            message, calls = assistant_message(raw)
            assert len(calls) == 1 and calls[0].name == name
            call = calls[0]
            jsonschema.validate(
                call.arguments,
                next(
                    d["function"]["parameters"]
                    for d in definitions
                    if d["function"]["name"] == name
                ),
            )
            assert call.id not in ids
            ids.append(call.id)
            messages.append(message)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(
                        {"city": "台北", "indoor_place": "城市圖書館", "weather": "下雨"}
                    ),
                }
            )
        raw, usage = await provider.completion_with_usage(
            messages, tools=definitions if multi else definitions[:1]
        )
        message, calls = assistant_message(raw)
        assert not calls and message.get("content", "").strip()
        return {
            "response_shape": "assistant/tool/assistant",
            "tool_call_count": len(ids),
            "provider_usage": usage.model_dump(),
        }

    async def embeddings():
        provider.claim()
        vectors = await CloudflareEmbedder(provider).embed(["繁體中文學習", "English learning"])
        assert len(vectors) == 2 and len(vectors[0]) == len(vectors[1])
        return {
            "response_shape": "ordered finite vectors",
            "dimension": len(vectors[0]),
            "provider_usage": {"source": "unknown"},
        }

    for case, label, operation in [
        ("P01", "messages", normal),
        ("P02", "stream", stream),
        ("P03", "json_schema", structured),
        ("P04", "single tool", tools),
        ("P05", "multi tool", lambda: tools(True)),
        ("P06", "embeddings", embeddings),
    ]:
        row = {
            "case": case,
            "checked_at": datetime.now(UTC).isoformat(),
            "model": {"P02": CONVERSATION_MODEL, "P06": EMBEDDING_MODEL}.get(case, CHAT_MODEL),
            "request_schema": label,
            "status": "not_run",
        }
        started = time.monotonic()
        if not provider.stopped and provider.requests < provider.limit:
            try:
                row.update(await operation(), status="passed")
            except ProviderFailure as failure:
                row.update(status="failed", failure_class=failure.code)
                if failure.code == "rate_limited":
                    provider.stopped = True
            except Exception:
                row.update(status="failed", failure_class="capability_mismatch")
        row["duration_ms"] = round((time.monotonic() - started) * 1000)
        row["requests_total"] = provider.requests
        rows.append(row)
        print(case, row["status"], flush=True)
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--env-file", type=Path, default=ROOT / ".env")
    args = parser.parse_args()
    try:
        load_personal_config(args.env_file)
    except RuntimeError:
        print("Live 未執行：個人設定尚未就緒。")
        raise SystemExit(3) from None
    rows = asyncio.run(spike(BudgetedProvider(CloudflareSettings.from_environment())))
    artifact = (
        ROOT
        / "artifacts"
        / ("live-spike-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + ".json")
    )
    artifact.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n")
    if any(row["status"] != "passed" for row in rows):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
