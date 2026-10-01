import asyncio
import json
import os
from pathlib import Path

import httpx
import pytest
from database_helper import restart_database

from agent_lab_api.embeddings import EmbeddingFailure
from agent_lab_api.knowledge import KnowledgeConflict, KnowledgeStore
from agent_lab_api.main import app, get_embedder, get_provider, lifespan
from agent_lab_api.providers import FakeProvider
from agent_lab_api.rag_models import RetrievalOptions
from agent_lab_api.repository import Repository

pytestmark = pytest.mark.integration
ROOT = Path(__file__).resolve().parents[3]


class FixedEmbedder:
    model = "fixture/fixed-3"
    version = "1"

    async def embed(self, texts):
        return [[1, 0, 0] if "match" in text else [0, 1, 0] for text in texts]


@pytest.fixture(autouse=True)
async def isolated_knowledge():
    assert os.environ.get("AGENT_LAB_DB_NAME", "").startswith("lab_test_")
    if native := os.environ.get("AGENT_LAB_TEST_NATIVE_DIR"):
        data = await asyncio.to_thread(Path(native).resolve)
        assert data.parent.parent == ROOT / "artifacts"
        assert data.parent.name.startswith("ai-agent-lab-test-") and data.name == "data"
    else:
        assert os.environ.get("AGENT_LAB_TEST_CONTAINER", "").startswith("ai-agent-lab-test-")
    repo = Repository()
    yield repo
    app.dependency_overrides.clear()
    async with repo.connection() as db:
        await db.execute("TRUNCATE agent_lab.documents CASCADE")
        await db.execute("DELETE FROM agent_lab.embedding_profile")
        await db.execute("TRUNCATE agent_lab.conversations CASCADE")


@pytest.fixture
async def client(monkeypatch):
    monkeypatch.setenv("AGENT_LAB_PERSISTENCE", "1")
    app.dependency_overrides[get_embedder] = FixedEmbedder
    async with (
        lifespan(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://local"
        ) as client,
    ):
        yield client


async def test_pgvector_status_filter_topk_threshold_delete_and_duplicates(isolated_knowledge):
    store = KnowledgeStore(isolated_knowledge)
    embedder = FixedEmbedder()
    general = await store.ingest("general.md", "match general", "general", embedder)
    single = await store.ingest("single.md", "match single", "single", embedder)
    married = await store.ingest("married.md", "match married", "married", embedder)
    await store.ingest("irrelevant.md", "irrelevant", "single", embedder)
    duplicate = await store.ingest("renamed.md", "match single", "single", embedder)
    assert duplicate.id == single.id and len(await store.list()) == 4
    _, found = await store.search("match", RetrievalOptions(relationship_status="single"), embedder)
    assert {item.document_id for item in found} == {general.id, single.id}
    assert married.id not in {item.document_id for item in found}
    _, top = await store.search("match", RetrievalOptions(top_k=1, threshold=1), embedder)
    assert len(top) == 1 and top[0].score == 1
    await store.delete(single.id)
    async with isolated_knowledge.connection() as db:
        assert (
            await (
                await db.execute(
                    "SELECT count(*) AS n FROM agent_lab.chunks WHERE document_id=%s", (single.id,)
                )
            ).fetchone()
        )["n"] == 0
    _, filtered = await store.search(
        "match", RetrievalOptions(relationship_status="single"), embedder
    )
    assert {item.document_id for item in filtered} == {general.id}


async def test_embedding_profile_change_requires_explicit_reindex(isolated_knowledge):
    store = KnowledgeStore(isolated_knowledge)
    await store.ingest("a.md", "match", "single", FixedEmbedder())

    class Changed(FixedEmbedder):
        version = "2"

        async def embed(self, texts):
            return [[1, 0, 0, 0] for _ in texts]

    changed = Changed()
    with pytest.raises(KnowledgeConflict):
        await store.search("match", RetrievalOptions(), changed)
    with pytest.raises(KnowledgeConflict):
        await store.ingest("b.md", "new", "single", changed)
    docs = await store.reindex(changed)
    assert docs[0].embedding_dimension == 4 and docs[0].embedding_version == "2"
    _, found = await store.search("match", RetrievalOptions(), changed)
    assert len(found) == 1


async def test_failed_embedding_import_is_atomic(client):
    class Broken(FixedEmbedder):
        async def embed(self, texts):
            return [[0, 0, 0] for _ in texts]

    app.dependency_overrides[get_embedder] = Broken
    response = await client.post("/documents", files={"file": ("x.md", b"match")})
    assert response.status_code == 502
    assert (await client.get("/documents")).json() == []


async def test_duplicate_import_avoids_embedding_and_namespace_change_is_rejected(
    isolated_knowledge,
):
    store = KnowledgeStore(isolated_knowledge)
    original = await store.ingest("a.md", "match same text", "single", FixedEmbedder())

    class NoCall(FixedEmbedder):
        async def embed(self, texts):
            raise AssertionError("Duplicate import must not call embedding provider")

    assert (await store.ingest("b.md", "match same text", "single", NoCall())).id == original.id
    changed = NoCall()
    changed.version = "2"
    with pytest.raises(KnowledgeConflict):
        await store.ingest("b.md", "match same text", "single", changed)


async def test_rag_preserves_original_question_and_sources_in_storage(client, isolated_knowledge):
    seen = []

    class Rewriter(FakeProvider):
        async def rewrite(self, messages):
            return "match REWRITTEN_SEARCH_ONLY"

        async def stream(self, messages, scenario):
            seen.append(messages)
            async for text in super().stream(messages, scenario):
                yield text

    app.dependency_overrides[get_provider] = Rewriter
    document = (
        await client.post(
            "/documents",
            data={"relationship_status": "single"},
            files={"file": ("source.md", b"match SOURCE_EVIDENCE")},
        )
    ).json()
    first = (await client.post("/conversations", json={"title": "A"})).json()["id"]
    second = (await client.post("/conversations", json={"title": "B"})).json()["id"]
    await client.post(f"/conversations/{first}/chat", json={"message": "先前的溝通背景"})
    original = "他這樣說，我該如何回應？"
    response = await client.post(
        f"/conversations/{first}/rag", json={"message": original, "relationship_status": "single"}
    )
    assert "event: done" in response.text
    assert seen[-1][-1].content == original
    assert "REWRITTEN_SEARCH_ONLY" not in seen[-1][-1].content
    snapshots = (await client.get(f"/conversations/{first}/retrievals")).json()
    assert len(snapshots) == 1 and snapshots[0]["original_question"] == original
    assert snapshots[0]["retrieval_query"] == "match REWRITTEN_SEARCH_ONLY"
    assert snapshots[0]["citations"][0]["document_id"] == document["id"]
    assert (await client.get(f"/conversations/{second}/retrievals")).json() == []
    # A fresh repository reads persisted rows, independent of request/provider object lifetime.
    from uuid import UUID

    from agent_lab_api.rag import RetrievalStore

    assert (await RetrievalStore(Repository()).list(UUID(first)))[0].original_question == original
    assert (await client.delete(f"/documents/{document['id']}")).status_code == 204
    assert (await client.get(f"/conversations/{first}/retrievals")).json() == snapshots
    assert (await client.delete(f"/conversations/{first}")).status_code == 204
    async with isolated_knowledge.connection() as db:
        assert (
            await (await db.execute("SELECT count(*) AS n FROM agent_lab.retrievals")).fetchone()
        )["n"] == 0


async def test_empty_results_and_failed_retrieval_remain_distinct(client):
    first = (await client.post("/conversations", json={"title": "empty"})).json()["id"]
    response = await client.post(f"/conversations/{first}/rag", json={"message": "match"})
    assert "event: done" in response.text and "知識庫未找到" in response.text
    snapshot = (await client.get(f"/conversations/{first}/retrievals")).json()
    assert snapshot[0]["citations"] == []

    class Failed(FixedEmbedder):
        async def embed(self, texts):
            raise EmbeddingFailure("INTERNAL_DETAIL")

    app.dependency_overrides[get_embedder] = Failed
    response = await client.post(f"/conversations/{first}/rag", json={"message": "match"})
    events = [
        json.loads(line[6:]) for line in response.text.splitlines() if line.startswith("data: ")
    ]
    assert events[-1]["type"] == "error" and "INTERNAL_DETAIL" not in response.text
    turns = (await client.get(f"/conversations/{first}")).json()["turns"]
    assert [turn["status"] for turn in turns] == ["completed", "failed"]
    assert len((await client.get(f"/conversations/{first}/retrievals")).json()) == 1


async def test_document_validation_and_zero_results_threshold(client):
    assert (
        await client.post("/documents", files={"file": ("bad.txt", b"text")})
    ).status_code == 422
    assert (
        await client.post(
            "/documents",
            data={"relationship_status": "unknown"},
            files={"file": ("ok.md", b"text")},
        )
    ).status_code == 422
    await client.post("/documents", files={"file": ("ok.md", b"irrelevant")})
    response = await client.post("/retrieval", json={"query": "match", "threshold": 0.1})
    assert response.status_code == 200 and response.json()["citations"] == []


async def test_documents_profile_and_vectors_survive_real_database_restart(isolated_knowledge):
    store = KnowledgeStore(isolated_knowledge)
    original = await store.ingest("persist.md", "match RESTART_DOCUMENT", "single", FixedEmbedder())
    await restart_database(isolated_knowledge)
    fresh = KnowledgeStore(Repository())
    documents = await fresh.list()
    assert len(documents) == 1 and documents[0].id == original.id
    profile, citations = await fresh.search("match", RetrievalOptions(), FixedEmbedder())
    assert profile.dimension == 3 and citations[0].document_id == original.id
