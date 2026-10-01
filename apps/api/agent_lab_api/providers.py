import asyncio
import json
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from typing import Protocol

from .contracts import ErrorCode, Scenario
from .conversation_models import PromptMessage


@dataclass
class ProviderFailure(Exception):
    code: ErrorCode
    message: str
    retryable: bool


class StreamingProvider(Protocol):
    def stream(self, messages: list[PromptMessage], scenario: Scenario) -> AsyncGenerator[str]: ...

    async def report(self, messages: list[PromptMessage]) -> object: ...

    async def rewrite(self, messages: list[PromptMessage]) -> str: ...


class FakeProvider:
    """Deterministic learning responses, with no external calls or credentials."""

    async def stream(
        self, messages: list[PromptMessage], scenario: Scenario
    ) -> AsyncGenerator[str]:
        failures: dict[str, ProviderFailure] = {
            "rate_limit": ProviderFailure("rate_limited", "請求過於頻繁，請稍後再試。", True),
            "quota": ProviderFailure("quota_exhausted", "免費額度已用完，請等待額度重置。", False),
            "timeout": ProviderFailure("provider_timeout", "回覆逾時，請稍後再試。", True),
            "dependency_failure": ProviderFailure(
                "dependency_failure", "服務暫時無法使用，請稍後再試。", True
            ),
        }
        if scenario in failures:
            raise failures[scenario]
        questions = [message.content for message in messages if message.role == "user"]
        fragments = [
            f"你說：「{questions[-1]}」\n",
            (f"我記得你先前提到：「{questions[-2]}」。\n" if len(questions) > 1 else "")
            + "我們可以先釐清彼此的期待，再用尊重界線的小步驟練習溝通。",
            "\n這是離線示範回覆，方便觀察串流與取消。",
        ]
        evidence = next(
            (
                m.content.split("RAG_EVIDENCE:\n", 1)[1]
                for m in messages
                if m.role == "system" and "RAG_EVIDENCE:\n" in m.content
            ),
            None,
        )
        if evidence is not None:
            citations = json.loads(evidence)
            fragments = [
                f"你說：「{questions[-1]}」\n",
                *(
                    [f"[{i + 1}] {citation['content']}\n" for i, citation in enumerate(citations)]
                    if citations
                    else ["知識庫未找到相關資料，請補充背景或匯入適合的文件。\n"]
                ),
                "這是離線檢索示範，尚未使用真模型。",
            ]
        if scenario == "slow":
            fragments = fragments[:1] + ["接著，一步一步觀察回覆。"] * 40
        for index, fragment in enumerate(fragments):
            if index:
                await asyncio.sleep(0.25 if scenario == "slow" else 0.04)
            yield fragment

    async def rewrite(self, messages: list[PromptMessage]) -> str:
        questions = [m.content for m in messages if m.role == "user"]
        current = questions[-1]
        if len(questions) > 1 and any(word in current for word in ("他", "她", "這樣", "那麼")):
            return (questions[-2] + " " + current)[-2000:]
        return current

    async def report(self, messages: list[PromptMessage]) -> object:
        question = next(message.content for message in reversed(messages) if message.role == "user")
        return {
            "title": "你的戀愛溝通練習報告（離線示範）",
            "suggestions": [
                f"先整理你提到的「{question[:120]}」，區分事實與自己的感受。",
                "用一個具體問題確認對方的期待，避免替對方猜想。",
                "約定一個雙方願意嘗試的小步驟，再回顧溝通效果。",
            ],
        }
