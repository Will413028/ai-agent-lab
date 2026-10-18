"""SDK-backed Workers AI adapter; no retries, paid fallback, or reasoning exposure."""

import asyncio
import json
import os
import re
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field

import httpx
from openai import APIStatusError, APITimeoutError, AsyncOpenAI, OpenAIError

from .contracts import Scenario
from .conversation_models import LoveReport, PromptMessage
from .embeddings import EmbeddingFailure, validate_vectors
from .providers import ProviderFailure

CHAT_MODEL = "@cf/zai-org/glm-4.7-flash"
EMBEDDING_MODEL = "@cf/baai/bge-m3"
MAX_RESPONSE_BYTES = 2 * 1024 * 1024


@dataclass(frozen=True)
class CloudflareSettings:
    account_id: str = field(repr=False)
    token: str = field(repr=False)
    chat_model: str = CHAT_MODEL
    embedding_model: str = EMBEDDING_MODEL
    thinking: bool = False

    @classmethod
    def from_environment(cls, environment=None):
        environment = os.environ if environment is None else environment
        account = environment.get("CLOUDFLARE_ACCOUNT_ID", "")
        token = environment.get("CLOUDFLARE_API_TOKEN", "")
        if not re.fullmatch(r"[a-fA-F0-9]{32}", account) or not token:
            raise RuntimeError(
                "Set personal Cloudflare server credentials before enabling live mode"
            )
        chat = environment.get("AGENT_LAB_CHAT_MODEL", CHAT_MODEL)
        embedding = environment.get("AGENT_LAB_EMBEDDING_MODEL", EMBEDDING_MODEL)
        if chat != CHAT_MODEL or embedding != EMBEDDING_MODEL:
            raise RuntimeError("Model is outside the verified free-model allowlist")
        # Off by default: with reasoning on, GLM spent the whole 2048-token budget and
        # returned no content in live holdout (2026-10-18, Will chose off).
        thinking = environment.get("AGENT_LAB_THINKING", "off")
        if thinking not in ("on", "off"):
            raise RuntimeError("AGENT_LAB_THINKING must be on or off")
        return cls(account, token, chat, embedding, thinking == "on")

    def chat_options(self) -> dict:
        # Undocumented on Workers AI but measured effective for GLM-4.7-flash (D6b probe).
        if self.thinking:
            return {}
        return {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}

    @property
    def base_url(self):
        return f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}/ai/v1/"


def mapped_status(status: int) -> ProviderFailure:
    if status == 429:
        return ProviderFailure("rate_limited", "Cloudflare 請求或免費額度受限，請稍後再試。", False)
    if status in (401, 403):
        return ProviderFailure("dependency_failure", "Cloudflare 設定或權限尚未就緒。", False)
    return ProviderFailure("provider_failure", "Cloudflare 暫時無法完成請求。", False)


class BoundedStream(httpx.AsyncByteStream):
    def __init__(self, stream: httpx.AsyncByteStream):
        self.stream = stream

    async def __aiter__(self):
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            if size > MAX_RESPONSE_BYTES:
                raise ProviderFailure("provider_failure", "模型回應超過上限。", False)
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


async def bound_response(response: httpx.Response):
    response.stream = BoundedStream(response.stream)


def map_failure(failure: Exception) -> ProviderFailure:
    if isinstance(failure, APIStatusError):
        return mapped_status(failure.status_code)
    if isinstance(failure, (APITimeoutError, TimeoutError)):
        return ProviderFailure("provider_timeout", "Cloudflare 回覆逾時。", False)
    return ProviderFailure("provider_failure", "Cloudflare 回覆格式不正確或未完整結束。", False)


class CloudflareProvider:
    def __init__(self, settings: CloudflareSettings, *, transport=None):
        self.settings = settings
        self.transport = transport

    def client(self):
        return AsyncOpenAI(
            api_key=self.settings.token,
            base_url=self.settings.base_url,
            max_retries=0,
            timeout=httpx.Timeout(45, connect=5),
            http_client=httpx.AsyncClient(
                timeout=httpx.Timeout(45, connect=5),
                transport=self.transport,
                follow_redirects=False,
                trust_env=False,
                event_hooks={"response": [bound_response]},
            ),
        )

    async def completion(self, messages: list[dict], **options) -> dict:
        message, _ = await self.completion_with_usage(messages, **options)
        return message

    async def completion_with_usage(self, messages: list[dict], **options):
        from .run_models import Usage

        try:
            async with asyncio.timeout(60), self.client() as client:
                result = await client.chat.completions.create(
                    model=self.settings.chat_model,
                    messages=messages,
                    **{"max_completion_tokens": 2048, **self.settings.chat_options(), **options},
                )
            choice = result.choices[0]
            if choice.finish_reason not in ("stop", "tool_calls"):
                raise ValueError
            # Allowlist prevents reasoning fields from reaching persistence, logs, or consumers.
            message = choice.message.model_dump(
                include={"role", "content", "tool_calls"}, exclude_none=True
            )
            usage = Usage()
            if result.usage is not None:
                values = (result.usage.prompt_tokens, result.usage.completion_tokens)
                if all(type(value) is int and value >= 0 for value in values):
                    usage = Usage(
                        source="provider", input_tokens=values[0], output_tokens=values[1]
                    )
            return message, usage
        except (
            OpenAIError,
            TimeoutError,
            KeyError,
            IndexError,
            TypeError,
            ValueError,
            AttributeError,
        ) as failure:
            raise map_failure(failure) from None

    async def stream(
        self, messages: list[PromptMessage], scenario: Scenario
    ) -> AsyncGenerator[str]:
        if scenario != "normal":
            raise ProviderFailure("provider_failure", "Live 模式不使用離線錯誤情境。", False)
        try:
            async with asyncio.timeout(60), self.client() as client:
                stream = await client.chat.completions.create(
                    model=self.settings.chat_model,
                    messages=[m.model_dump() for m in messages],
                    stream=True,
                    max_completion_tokens=2048,
                    **self.settings.chat_options(),
                )
                async with stream:
                    finished = False
                    async for chunk in stream:
                        if not chunk.choices:
                            continue
                        choice = chunk.choices[0]
                        content = choice.delta.content
                        if content is not None:
                            if not isinstance(content, str):
                                raise ValueError
                            if content:
                                yield content
                        if choice.finish_reason:
                            if choice.finish_reason != "stop":
                                raise ValueError
                            finished = True
                    if not finished:
                        raise ValueError
        except (
            OpenAIError,
            TimeoutError,
            ValueError,
            TypeError,
            KeyError,
            IndexError,
            AttributeError,
        ) as failure:
            raise map_failure(failure) from None

    async def report(self, messages: list[PromptMessage]) -> object:
        output = await self.completion(
            [m.model_dump() for m in messages]
            + [
                {
                    "role": "user",
                    "content": (
                        "根據以上對話產生繁體中文報告，含 title 與 1–5 項 suggestions，"
                        "不加入其他欄位。每項建議都要符合使用者說過的時間、預算與溝通限制："
                        "需要雙方同時進行的事，只能排在使用者說有空的時段；"
                        "其他時間只建議不需同步的做法。不推定對話沒提到的人（例如子女、長輩）"
                        "或對方的想法。"
                    ),
                }
            ],
            # GLM-4.7-flash is not on the Workers AI JSON mode list and json_schema timed out
            # live (D6b, 2026-10-18); one forced tool call carries the schema instead.
            tools=[
                {
                    "type": "function",
                    "function": {
                        "name": "submit_report",
                        "description": "提交繁體中文報告。",
                        "parameters": LoveReport.model_json_schema(),
                    },
                }
            ],
            tool_choice="required",
            parallel_tool_calls=False,
        )
        calls = output.get("tool_calls") or []
        if len(calls) != 1 or calls[0]["function"]["name"] != "submit_report":
            # None fails LoveReport validation in the endpoint: 502 invalid_report.
            return None
        try:
            return json.loads(calls[0]["function"]["arguments"])
        except (ValueError, TypeError):
            return None

    async def rewrite(self, messages: list[PromptMessage]) -> str:
        output = await self.completion(
            [
                {
                    "role": "system",
                    "content": "只輸出一個繁體中文檢索查詢。根據對話補足最後問題的代名詞，"
                    "保留原意，不回答問題，不加入說明，最長 2000 字。",
                },
                *[m.model_dump() for m in messages if m.role != "system"],
            ],
            max_completion_tokens=512,
        )
        content = output.get("content")
        if not isinstance(content, str) or not content.strip() or len(content) > 2000:
            raise ProviderFailure("provider_failure", "模型檢索查詢格式不正確。", False)
        return content.strip()


class CloudflareEmbedder:
    model = EMBEDDING_MODEL

    def __init__(self, provider: CloudflareProvider):
        self.provider = provider
        self.model = provider.settings.embedding_model
        # Workers AI does not expose immutable model revisions; explicit local epoch is recorded.
        self.version = os.environ.get("AGENT_LAB_EMBEDDING_VERSION", "provider-unversioned-epoch1")

    async def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        try:
            async with asyncio.timeout(120), self.provider.client() as client:
                for start in range(0, len(texts), 16):
                    batch = texts[start : start + 16]
                    result = await client.embeddings.create(
                        model=self.model, input=batch, encoding_format="float"
                    )
                    data = sorted(result.data, key=lambda row: row.index)
                    if [row.index for row in data] != list(range(len(batch))):
                        raise ValueError
                    vectors.extend(validate_vectors([row.embedding for row in data], len(batch)))
        except (OpenAIError, TimeoutError) as failure:
            raise map_failure(failure) from None
        except (KeyError, TypeError, ValueError, AttributeError):
            raise EmbeddingFailure("Invalid Cloudflare embedding response") from None
        return validate_vectors(vectors, len(texts))
