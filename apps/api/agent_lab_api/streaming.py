import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import aclosing
from uuid import uuid4

import anyio
from fastapi.responses import StreamingResponse

from .contracts import DeltaEvent, DoneEvent, ErrorEvent, Scenario, encode_event
from .conversation_models import PromptMessage
from .providers import ProviderFailure, StreamingProvider

Persist = Callable[[str, str, str | None], Awaitable[None]]


async def chat_events(
    provider: StreamingProvider,
    messages: list[PromptMessage],
    scenario: Scenario,
    persist: Persist | None = None,
) -> AsyncGenerator[DeltaEvent | DoneEvent | ErrorEvent]:
    request_id = uuid4()
    sequence = 0
    answer = ""
    saved = False
    state = "cancelled"
    code: str | None = None
    try:
        try:
            async with aclosing(provider.stream(messages, scenario)) as output:
                async for text in output:
                    if len(answer) + len(text) > 16000:
                        raise ProviderFailure(
                            "provider_failure", "回覆超過長度上限，請縮小問題後再試。", False
                        )
                    answer += text
                    yield DeltaEvent(
                        version=1, type="delta", request_id=request_id, sequence=sequence, text=text
                    )
                    sequence += 1
            if persist is not None:
                await persist(answer, "completed", None)
            saved = True
            yield DoneEvent(
                version=1, type="done", request_id=request_id, sequence=sequence, usage=None
            )
        except asyncio.CancelledError:
            raise
        except Exception as failure:
            state = "failed"
            mapped = (
                failure
                if isinstance(failure, ProviderFailure)
                else ProviderFailure("provider_failure", "無法取得回覆，請稍後再試。", False)
            )
            code = mapped.code
            if persist is not None:
                try:
                    await persist(answer, state, code)
                    saved = True
                except Exception:
                    mapped = ProviderFailure(
                        "dependency_failure", "對話儲存暫時無法使用，請稍後再試。", True
                    )
            yield ErrorEvent(
                version=1,
                type="error",
                request_id=request_id,
                sequence=sequence,
                code=mapped.code,
                message=mapped.message,
                retryable=mapped.retryable,
            )
    finally:
        if persist is not None and not saved:
            # Bounded cleanup survives ASGI disconnect cancellation; no background continuation.
            with anyio.CancelScope(shield=True), anyio.move_on_after(2):
                try:
                    await persist(answer, state, code)
                except Exception:
                    pass  # Singleton startup recovery marks an unfinalized turn interrupted.


def chat_response(
    provider: StreamingProvider,
    messages: list[PromptMessage],
    scenario: Scenario,
    persist: Persist | None = None,
) -> StreamingResponse:
    async def encoded() -> AsyncGenerator[str]:
        async with aclosing(chat_events(provider, messages, scenario, persist)) as events:
            async for event in events:
                yield encode_event(event)

    return StreamingResponse(
        encoded(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )
