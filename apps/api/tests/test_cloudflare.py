import json

import httpx
import pytest

from agent_lab_api.cloudflare import (
    MAX_RESPONSE_BYTES,
    CloudflareEmbedder,
    CloudflareProvider,
    CloudflareSettings,
)
from agent_lab_api.context import build_context
from agent_lab_api.embeddings import EmbeddingFailure
from agent_lab_api.providers import ProviderFailure


def provider(handler):
    # Artificial placeholders only. No account token is loaded by these tests.
    return CloudflareProvider(
        CloudflareSettings("0" * 32, "fixture-placeholder"), transport=httpx.MockTransport(handler)
    )


async def test_stream_content_only_and_explicit_finish():
    def handler(request):
        payload = json.loads(request.content)
        assert payload["stream"] and payload["messages"][-1]["content"] == "你好"
        return httpx.Response(
            200,
            text='data: {"choices":[{"delta":{"reasoning_content":"PRIVATE_REASONING"},'
            '"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{"content":"繁體中文🙂"},"finish_reason":null}]}\n\n'
            'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            "data: [DONE]\n\n",
        )

    assert [
        item async for item in provider(handler).stream(build_context([], "你好"), "normal")
    ] == ["繁體中文🙂"]


@pytest.mark.parametrize(
    "text",
    [
        'data: {"choices":[{"delta":{"content":"半句"},"finish_reason":null}]}\n\n',
        'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\n',
        "data: bad json\n\n",
    ],
)
async def test_incomplete_stream_fails(text):
    with pytest.raises(ProviderFailure):
        _ = [
            item
            async for item in provider(lambda _: httpx.Response(200, text=text)).stream(
                build_context([], "hi"), "normal"
            )
        ]


async def test_embeddings_preserve_input_order_and_validate_dimensions():
    def handler(request):
        assert str(request.url).endswith("/embeddings")
        assert json.loads(request.content)["input"] == ["a", "b"]
        return httpx.Response(
            200,
            json={
                "data": [{"index": 1, "embedding": [0, 1, 0]}, {"index": 0, "embedding": [1, 0, 0]}]
            },
        )

    assert await CloudflareEmbedder(provider(handler)).embed(["a", "b"]) == [[1, 0, 0], [0, 1, 0]]
    with pytest.raises(EmbeddingFailure):
        await CloudflareEmbedder(
            provider(
                lambda _: httpx.Response(200, json={"data": [{"index": 0, "embedding": [0, 0, 0]}]})
            )
        ).embed(["a"])


@pytest.mark.parametrize(
    "status,code",
    [
        (429, "rate_limited"),
        (401, "dependency_failure"),
        (403, "dependency_failure"),
        (500, "provider_failure"),
    ],
)
async def test_provider_errors_are_sanitized_and_not_retried(status, code):
    calls = 0

    def handler(_):
        nonlocal calls
        calls += 1
        return httpx.Response(status, text="UNTRUSTED_TOKEN_AND_PROVIDER_DETAIL")

    with pytest.raises(ProviderFailure) as error:
        await provider(handler).completion([{"role": "user", "content": "hi"}])
    assert error.value.code == code
    assert "UNTRUSTED" not in str(error.value) and calls == 1


async def test_completion_strips_reasoning():
    model = provider(
        lambda _: httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "role": "assistant",
                            "content": "答案",
                            "reasoning_content": "PRIVATE_REASONING",
                        },
                    }
                ]
            },
        )
    )
    assert await model.completion([]) == {"role": "assistant", "content": "答案"}


def test_credentials_repr_and_missing_configuration(monkeypatch):
    assert "fixture-placeholder" not in repr(CloudflareSettings("0" * 32, "fixture-placeholder"))
    monkeypatch.delenv("CLOUDFLARE_ACCOUNT_ID", raising=False)
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="personal Cloudflare"):
        CloudflareSettings.from_environment()


async def test_sdk_transport_byte_limit_closes_response():
    closed = False

    class TooLarge(httpx.AsyncByteStream):
        async def __aiter__(self):
            yield b"x" * (MAX_RESPONSE_BYTES + 1)

        async def aclose(self):
            nonlocal closed
            closed = True

    model = provider(lambda _: httpx.Response(200, stream=TooLarge()))
    with pytest.raises(ProviderFailure):
        await model.completion([])
    assert closed
