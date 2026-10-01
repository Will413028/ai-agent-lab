import math

import pytest

from agent_lab_api.context import build_context
from agent_lab_api.embeddings import EmbeddingFailure, FixtureEmbedder, validate_vectors
from agent_lab_api.knowledge import (
    CHUNK_SIZE,
    MAX_UPLOAD_BYTES,
    keywords,
    read_markdown,
    split_markdown,
)
from agent_lab_api.rag import evidence_context, retrieve
from agent_lab_api.rag_models import EmbeddingProfile, RetrievalOptions, RetrievalResult


def test_markdown_limits_and_utf8():
    assert read_markdown("hello.md", b"\xef\xbb\xbf# hi\r\n\r\nhello") == "# hi\n\nhello"
    for name, raw in [
        ("../file.md", b"ok"),
        ("x.txt", b"ok"),
        ("x.md", b"\xff"),
        ("x.md", b" "),
        ("x.md", b"nul\0"),
        ("x.md", b"a" * (MAX_UPLOAD_BYTES + 1)),
    ]:
        with pytest.raises(ValueError):
            read_markdown(name, raw)


def test_chunking_keeps_paragraphs_and_long_text():
    text = "# 標題\n\n第一段🙂\n\n" + "長內容" * 700
    chunks = split_markdown(text)
    assert chunks[0] == "# 標題\n\n第一段🙂"
    assert all(0 < len(chunk) <= CHUNK_SIZE for chunk in chunks)
    rebuilt = chunks[1] + "".join(chunk[80:] for chunk in chunks[2:])
    assert rebuilt == "長內容" * 700
    assert keywords("# 溝通練習\n\ncommunication communication boundaries") == [
        "溝通練習",
        "communication",
        "boundaries",
    ]
    with pytest.raises(ValueError):
        split_markdown("x" * 140000)


@pytest.mark.parametrize(
    "raw,count",
    [
        ([], 1),
        ([[1]], 2),
        ([[0, 0]], 1),
        ([[True]], 1),
        ([[math.nan]], 1),
        ([[math.inf]], 1),
        ([[1], [1, 2]], 2),
    ],
)
def test_invalid_vectors_are_rejected(raw, count):
    with pytest.raises(EmbeddingFailure):
        validate_vectors(raw, count)


async def test_fixture_embedding_is_repeatable_and_lexical():
    embedder = FixtureEmbedder()
    a = await embedder.embed(["咖啡散步", "太空火箭"])
    assert a == await embedder.embed(["咖啡散步", "太空火箭"])
    assert len(a[0]) == 128
    assert sum(x * y for x, y in zip(a[0], a[1], strict=True)) < 0.5


def test_query_rewrite_is_never_the_generation_question():
    original = "他這樣說，我該怎麼回覆？"
    messages = build_context([], original)
    result = RetrievalResult(
        original_question=original,
        retrieval_query="REWRITTEN_SEARCH_ONLY",
        options=RetrievalOptions(),
        citations=[],
        profile=EmbeddingProfile(model="fixture", version="1", dimension=3),
    )
    context = evidence_context(messages, result)
    assert context[-1].role == "user" and context[-1].content == original
    assert "REWRITTEN_SEARCH_ONLY" not in str(context)
    assert "未受信任" in context[1].content


async def test_first_question_and_preview_do_not_call_rewriter():
    class NoRewrite:
        async def rewrite(self, messages):
            raise AssertionError("A standalone question has no history to resolve")

    class Store:
        async def search(self, query, options, embedder):
            assert query == "原問題"
            return EmbeddingProfile(model="fixture", version="1", dimension=3), []

    result = await retrieve(
        build_context([], "原問題"), RetrievalOptions(), NoRewrite(), FixtureEmbedder(), Store()
    )
    assert result.original_question == result.retrieval_query == "原問題"
