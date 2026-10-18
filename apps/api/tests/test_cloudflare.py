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


def report_response(message):
    return httpx.Response(
        200, json={"choices": [{"finish_reason": "tool_calls", "message": message}]}
    )


def report_call(arguments, name="submit_report"):
    return {"id": "call_0", "type": "function", "function": {"name": name, "arguments": arguments}}


async def test_report_uses_single_forced_tool_call_instead_of_json_mode():
    sent = {}

    def handler(request):
        sent.update(json.loads(request.content))
        return report_response(
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [report_call('{"title":"標題","suggestions":["一"]}')],
            }
        )

    report = await provider(handler).report(build_context([], "你好"))
    assert report == {"title": "標題", "suggestions": ["一"]}
    # GLM-4.7-flash is not on the Workers AI JSON mode list; json_schema timed out live.
    assert "response_format" not in sent
    assert sent["tool_choice"] == "required" and sent["parallel_tool_calls"] is False
    assert [tool["function"]["name"] for tool in sent["tools"]] == ["submit_report"]
    assert sent["tools"][0]["function"]["parameters"]["required"] == ["title", "suggestions"]


@pytest.mark.parametrize(
    "message",
    [
        {"role": "assistant", "content": "沒有呼叫工具"},
        {"role": "assistant", "tool_calls": [report_call("{}"), report_call("{}")]},
        {"role": "assistant", "tool_calls": [report_call("not json")]},
        {"role": "assistant", "tool_calls": [report_call("{}", name="other")]},
    ],
)
async def test_report_without_exactly_one_valid_call_is_invalid_report(message):
    # None fails LoveReport validation in the endpoint, which answers 502 invalid_report.
    assert (
        await provider(lambda _: report_response(message)).report(build_context([], "hi")) is None
    )


@pytest.mark.parametrize("value,sent", [(None, False), ("on", None), ("off", False)])
async def test_thinking_switch_applies_to_glm_and_stream_uses_llama(value, sent):
    environment = {"CLOUDFLARE_ACCOUNT_ID": "0" * 32, "CLOUDFLARE_API_TOKEN": "fixture-placeholder"}
    if value is not None:
        environment["AGENT_LAB_THINKING"] = value
    bodies = []

    def handler(request):
        payload = json.loads(request.content)
        bodies.append(payload)
        if payload.get("stream"):
            return httpx.Response(
                200,
                text='data: {"choices":[{"delta":{"content":"好"},"finish_reason":"stop"}]}\n\n'
                "data: [DONE]\n\n",
            )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"role": "assistant", "content": "好"}}
                ]
            },
        )

    model = CloudflareProvider(
        CloudflareSettings.from_environment(environment), transport=httpx.MockTransport(handler)
    )
    await model.completion([{"role": "user", "content": "hi"}])
    _ = [item async for item in model.stream(build_context([], "hi"), "normal")]
    completion, stream = bodies
    assert completion["model"] == "@cf/zai-org/glm-4.7-flash"
    assert completion.get("chat_template_kwargs", {}).get("enable_thinking") == sent
    # Chat and RAG answers stream from llama: GLM fabricated venues and prices in live holdout.
    assert stream["model"] == "@cf/meta/llama-3.3-70b-instruct-fp8-fast"
    assert "chat_template_kwargs" not in stream


def test_unknown_thinking_value_fails_fast():
    with pytest.raises(RuntimeError):
        CloudflareSettings.from_environment(
            {
                "CLOUDFLARE_ACCOUNT_ID": "0" * 32,
                "CLOUDFLARE_API_TOKEN": "fixture-placeholder",
                "AGENT_LAB_THINKING": "maybe",
            }
        )


def test_unknown_stream_model_fails_fast():
    with pytest.raises(RuntimeError):
        CloudflareSettings.from_environment(
            {
                "CLOUDFLARE_ACCOUNT_ID": "0" * 32,
                "CLOUDFLARE_API_TOKEN": "fixture-placeholder",
                "AGENT_LAB_STREAM_MODEL": "@cf/zai-org/glm-4.7-flash",
            }
        )


async def test_stream_keeps_numeric_content_tokens():
    # Workers AI llama streams numeric tokens as JSON numbers, e.g. "content": 44.
    text = (
        'data: {"choices":[{"delta":{"content":"預算"},"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{"content":600},"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{"content":"元"},"finish_reason":null}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
        "data: [DONE]\n\n"
    )
    pieces = [
        item
        async for item in provider(lambda _: httpx.Response(200, text=text)).stream(
            build_context([], "hi"), "normal"
        )
    ]
    assert "".join(pieces) == "預算600元"
