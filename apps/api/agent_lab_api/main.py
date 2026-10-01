import asyncio
import os
from contextlib import aclosing, asynccontextmanager
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from psycopg import Error as DatabaseError
from pydantic import ValidationError

from .agent_runtime import AgentRuntime, CloudflareRunModel, FakeRunModel, encode_run
from .artifacts import ToolFailure
from .cloudflare import CloudflareEmbedder, CloudflareProvider, CloudflareSettings
from .context import build_context
from .contracts import ChatRequest, ErrorEvent
from .conversation_models import (
    Conversation,
    ConversationDetail,
    LoveReport,
    NewConversation,
    SavedReport,
    Turn,
)
from .embeddings import Embedder, EmbeddingFailure, FixtureEmbedder
from .image_mcp import ImageMCP
from .image_models import ImageSearchRequest, ImageSearchResult
from .knowledge import MAX_UPLOAD_BYTES, KnowledgeConflict, KnowledgeStore, read_markdown
from .providers import FakeProvider, ProviderFailure, StreamingProvider
from .rag import RagProvider, RetrievalStore, retrieve
from .rag_models import (
    Document,
    RagRequest,
    RelationshipStatus,
    RetrievalOptions,
    RetrievalResult,
    SearchRequest,
    TurnRetrieval,
)
from .repository import Busy, NotFound, Repository, StaleReport
from .run_models import Run, RunRequest, RuntimeConfig
from .run_repository import RunStore
from .streaming import chat_events, chat_response
from .tool_models import Artifact, ToolDefinition, ToolRequest, ToolResult, Workspace
from .tools import ToolRegistry


def get_provider() -> StreamingProvider:
    if os.environ.get("AGENT_LAB_PROVIDER", "fake") == "cloudflare":
        return CloudflareProvider(CloudflareSettings.from_environment())
    return FakeProvider()


def get_embedder() -> Embedder:
    if os.environ.get("AGENT_LAB_PROVIDER", "fake") == "cloudflare":
        return CloudflareEmbedder(CloudflareProvider(CloudflareSettings.from_environment()))
    return FixtureEmbedder()


async def get_repository(request: Request) -> Repository:
    repository = getattr(request.app.state, "repository", None)
    lease = getattr(request.app.state, "lease", None)
    if repository is None or lease is None:
        raise HTTPException(
            status_code=503,
            detail={
                "code": "persistence_disabled",
                "message": "多輪儲存尚未啟用，請使用 make api 啟動服務。",
            },
        )
    try:
        await lease.execute("SELECT 1")
    except DatabaseError:
        request.app.state.repository = None
        raise
    return repository


@asynccontextmanager
async def lifespan(app: FastAPI):
    mode = os.environ.get("AGENT_LAB_PROVIDER", "fake")
    if mode not in ("fake", "cloudflare"):
        raise RuntimeError("Unknown provider mode")
    if mode == "cloudflare":
        CloudflareSettings.from_environment()
    for setting in ("AGENT_LAB_TOOLS", "AGENT_LAB_IMAGES"):
        if os.environ.get(setting, "fixture") not in ("fixture", "live"):
            raise RuntimeError("Unknown tool provider mode")
    app.state.repository = None
    app.state.lease = None
    app.state.active_runs = {}
    if os.environ.get("AGENT_LAB_PERSISTENCE") != "1":
        yield
        return
    repository = Repository()
    async with repository.connection(autocommit=True) as lease:
        cursor = await lease.execute(
            "SELECT pg_try_advisory_lock(hashtext('agent_lab.api')) AS held"
        )
        if not (await cursor.fetchone())["held"]:
            raise RuntimeError("Only one persistent API process may use this project database")
        await repository.recover_interrupted()
        await RunStore(repository).recover()
        app.state.repository = repository
        app.state.lease = lease
        try:
            yield
        finally:
            app.state.repository = None
            app.state.lease = None


app = FastAPI(title="AI Agent Lab", version="0.2.0", lifespan=lifespan)
Provider = Annotated[StreamingProvider, Depends(get_provider)]
Store = Annotated[Repository, Depends(get_repository)]
Embeddings = Annotated[Embedder, Depends(get_embedder)]


def get_tools() -> ToolRegistry:
    mode = os.environ.get("AGENT_LAB_TOOLS", "fixture")
    if mode not in ("fixture", "live"):
        raise RuntimeError("Unknown tools mode")
    return ToolRegistry(live=mode == "live")


Tools = Annotated[ToolRegistry, Depends(get_tools)]


def get_image_mcp() -> ImageMCP:
    mode = os.environ.get("AGENT_LAB_IMAGES", "fixture")
    if mode not in ("fixture", "live"):
        raise RuntimeError("Unknown image provider mode")
    return ImageMCP(mode)


Images = Annotated[ImageMCP, Depends(get_image_mcp)]


def get_run_model():
    if os.environ.get("AGENT_LAB_PROVIDER", "fake") == "cloudflare":
        return CloudflareRunModel(get_provider())
    return FakeRunModel()


RunModel = Annotated[FakeRunModel | CloudflareRunModel, Depends(get_run_model)]


@app.get("/runtime/config", response_model=RuntimeConfig)
def runtime_config():
    return RuntimeConfig(
        provider=os.environ.get("AGENT_LAB_PROVIDER", "fake"),
        tools_mode=os.environ.get("AGENT_LAB_TOOLS", "fixture"),
        images_mode=os.environ.get("AGENT_LAB_IMAGES", "fixture"),
        persistence_scope=(
            "disabled"
            if os.environ.get("AGENT_LAB_PERSISTENCE") != "1"
            else "test"
            if os.environ.get("AGENT_LAB_DB_NAME", "lab").startswith("lab_test_")
            else "development"
        ),
    )


@app.post("/conversations/{conversation_id}/runs/stream", response_class=StreamingResponse)
async def agent_run(
    conversation_id: UUID,
    body: RunRequest,
    request: Request,
    repository: Store,
    registry: Tools,
    images: Images,
    model: RunModel,
):
    store = RunStore(repository)
    run = await store.begin(conversation_id, body, registry.store.create())
    registry.add_images(images)
    runtime = AgentRuntime(model, registry)
    cancel = asyncio.Event()
    request.app.state.active_runs[run.id] = cancel

    async def stream():
        try:
            async with aclosing(encode_run(runtime, run, cancel, store.append)) as events:
                async for event in events:
                    yield event
        finally:
            request.app.state.active_runs.pop(run.id, None)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
    )


@app.get("/conversations/{conversation_id}/runs", response_model=list[Run])
async def list_runs(conversation_id: UUID, repository: Store):
    return await RunStore(repository).list(conversation_id)


@app.get("/conversations/{conversation_id}/runs/{run_id}", response_model=Run)
async def run_detail(conversation_id: UUID, run_id: UUID, repository: Store):
    return await RunStore(repository).get(conversation_id, run_id)


@app.post("/conversations/{conversation_id}/runs/{run_id}/cancel", response_model=Run)
async def cancel_run(conversation_id: UUID, run_id: UUID, request: Request, repository: Store):
    run = await RunStore(repository).get(conversation_id, run_id)
    signal = request.app.state.active_runs.get(run.id)
    if signal is not None:
        signal.set()
    return run


@app.get("/mcp/images/tools", response_model=list[ToolDefinition])
async def discover_image_tools(adapter: Images):
    return await adapter.discover()


@app.post("/mcp/images/search", response_model=ImageSearchResult)
async def search_images(body: ImageSearchRequest, adapter: Images):
    return await adapter.search(body.query)


@app.exception_handler(ToolFailure)
async def tool_failure(_request, failure):
    return JSONResponse(
        status_code=422,
        content={
            "detail": {
                "code": failure.code,
                "message": failure.message,
            }
        },
    )


@app.get("/tools", response_model=list[ToolDefinition])
async def tool_definitions(registry: Tools):
    return registry.definitions()


@app.post("/workspaces", response_model=Workspace, status_code=201)
async def create_workspace(registry: Tools):
    return Workspace(id=registry.store.create())


@app.get("/workspaces/{workspace_id}/artifacts", response_model=list[Artifact])
async def list_artifacts(workspace_id: UUID, registry: Tools):
    return registry.store.list(workspace_id)


@app.get("/workspaces/{workspace_id}/artifacts/{artifact_id}")
async def download_artifact(workspace_id: UUID, artifact_id: UUID, registry: Tools):
    artifact, path = registry.store.get(workspace_id, artifact_id)
    return FileResponse(
        path,
        media_type=artifact.media_type,
        filename=artifact.name,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@app.post("/tools/invoke", response_model=list[ToolResult])
async def invoke_tools(body: ToolRequest, registry: Tools):
    if len({call.id for call in body.calls}) != len(body.calls):
        raise HTTPException(status_code=422, detail="工具 call ID 不可重複。")
    # Sequential calls preserve dependency order; side effects are never retried.
    return [await registry.invoke(call, body.workspace_id) for call in body.calls]


@app.exception_handler(KnowledgeConflict)
async def knowledge_conflict(_request, _error):
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "code": "embedding_profile_changed",
                "message": "Embedding 設定或文件已變更，請明確重建索引。",
            }
        },
    )


@app.exception_handler(EmbeddingFailure)
async def embedding_failure(_request, _error):
    return JSONResponse(
        status_code=502,
        content={
            "detail": {
                "code": "invalid_embedding",
                "message": "Embedding 回傳格式不正確，匯入尚未寫入。",
            }
        },
    )


@app.exception_handler(ProviderFailure)
async def provider_failure(_request, error):
    return JSONResponse(
        status_code=503, content={"detail": {"code": error.code, "message": error.message}}
    )


@app.exception_handler(NotFound)
async def not_found(_request, _error):
    return JSONResponse(
        status_code=404, content={"detail": {"code": "not_found", "message": "找不到這個對話。"}}
    )


@app.exception_handler(Busy)
async def busy(_request, _error):
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "code": "conversation_busy",
                "message": "這個對話正在回覆，請先停止或等待完成。",
            }
        },
    )


@app.exception_handler(StaleReport)
async def stale(_request, _error):
    return JSONResponse(
        status_code=409,
        content={
            "detail": {
                "code": "report_conflict",
                "message": "請先完成一輪對話；若內容已變更，請重新產生報告。",
            }
        },
    )


@app.exception_handler(DatabaseError)
async def database_error(_request, _error):
    return JSONResponse(
        status_code=503,
        content={
            "detail": {
                "code": "storage_unavailable",
                "message": "對話儲存暫時無法使用，請確認資料庫已啟動。",
            }
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {
        "status": "ok",
        "mode": "cloudflare" if os.environ.get("AGENT_LAB_PROVIDER") == "cloudflare" else "offline",
    }


@app.post(
    "/chat",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def chat(body: ChatRequest, provider: Provider) -> StreamingResponse:
    return chat_response(provider, build_context([], body.message), body.scenario)


@app.get("/conversations", response_model=list[Conversation])
async def conversations(repository: Store):
    return await repository.list()


@app.post("/conversations", response_model=Conversation, status_code=201)
async def create_conversation(body: NewConversation, repository: Store):
    return await repository.create(body.title)


@app.get("/conversations/{conversation_id}", response_model=ConversationDetail)
async def conversation(conversation_id: UUID, repository: Store):
    return await repository.detail(conversation_id)


@app.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(conversation_id: UUID, repository: Store):
    await repository.delete(conversation_id)
    return Response(status_code=204)


@app.post(
    "/conversations/{conversation_id}/chat",
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {"schema": {"type": "string"}}}}},
)
async def conversation_chat(
    conversation_id: UUID, body: ChatRequest, repository: Store, provider: Provider
):
    turn, history = await repository.begin(conversation_id, body.message)

    async def persist(answer: str, status: str, code: str | None):
        await repository.finish(turn, answer, status, code)

    return chat_response(provider, build_context(history, body.message), body.scenario, persist)


@app.get("/documents", response_model=list[Document])
async def documents(repository: Store):
    return await KnowledgeStore(repository).list()


@app.post("/documents", response_model=Document, status_code=201)
async def import_document(
    repository: Store,
    embedder: Embeddings,
    file: Annotated[UploadFile, File()],
    relationship_status: Annotated[RelationshipStatus, Form()] = "general",
):
    try:
        content = await file.read(MAX_UPLOAD_BYTES + 1)
        markdown = read_markdown(file.filename or "", content)
        return await KnowledgeStore(repository).ingest(
            file.filename or "", markdown, relationship_status, embedder
        )
    except ValueError as failure:
        raise HTTPException(
            status_code=422, detail={"code": "invalid_document", "message": str(failure)}
        ) from failure
    finally:
        await file.close()


@app.delete("/documents/{document_id}", status_code=204)
async def delete_document(document_id: UUID, repository: Store):
    await KnowledgeStore(repository).delete(document_id)
    return Response(status_code=204)


@app.post("/documents/reindex", response_model=list[Document])
async def reindex_documents(repository: Store, embedder: Embeddings):
    return await KnowledgeStore(repository).reindex(embedder)


@app.post("/retrieval", response_model=RetrievalResult)
async def preview_retrieval(
    body: SearchRequest, repository: Store, provider: Provider, embedder: Embeddings
):
    return await retrieve(
        build_context([], body.query),
        RetrievalOptions(**body.model_dump(exclude={"query"})),
        provider,
        embedder,
        KnowledgeStore(repository),
    )


@app.get("/conversations/{conversation_id}/retrievals", response_model=list[TurnRetrieval])
async def conversation_retrievals(conversation_id: UUID, repository: Store):
    return await RetrievalStore(repository).list(conversation_id)


@app.post("/conversations/{conversation_id}/rag", response_class=StreamingResponse)
async def rag_chat(
    conversation_id: UUID,
    body: RagRequest,
    repository: Store,
    provider: Provider,
    embedder: Embeddings,
):
    turn, history = await repository.begin(conversation_id, body.message)
    options = RetrievalOptions(**body.model_dump(exclude={"message", "scenario"}))

    async def persist(answer: str, status: str, code: str | None):
        await repository.finish(turn, answer, status, code)

    return chat_response(
        RagProvider(provider, embedder, repository, turn, options),
        build_context(history, body.message),
        body.scenario,
        persist,
    )


@app.get("/conversations/{conversation_id}/reports", response_model=list[SavedReport])
async def reports(conversation_id: UUID, repository: Store):
    return await repository.reports(conversation_id)


@app.post("/conversations/{conversation_id}/reply", response_model=Turn)
async def synchronous_reply(
    conversation_id: UUID, body: ChatRequest, repository: Store, provider: Provider
):
    turn, history = await repository.begin(conversation_id, body.message)

    async def persist(answer: str, status: str, code: str | None):
        await repository.finish(turn, answer, status, code)

    async with aclosing(
        chat_events(provider, build_context(history, body.message), body.scenario, persist)
    ) as events:
        async for event in events:
            if isinstance(event, ErrorEvent):
                raise HTTPException(
                    status_code=503, detail={"code": event.code, "message": event.message}
                )
    detail = await repository.detail(conversation_id)
    return next(item for item in detail.turns if item.id == turn.id)


@app.post("/conversations/{conversation_id}/reports", response_model=SavedReport, status_code=201)
async def generate_report(conversation_id: UUID, repository: Store, provider: Provider):
    position, turns = await repository.report_source(conversation_id)
    try:
        raw = await provider.report(build_context(turns))
        report = LoveReport.model_validate(raw)
    except ValidationError as failure:
        raise HTTPException(
            status_code=502,
            detail={"code": "invalid_report", "message": "報告格式不正確，請重新嘗試。"},
        ) from failure
    except ProviderFailure as failure:
        raise HTTPException(
            status_code=503, detail={"code": failure.code, "message": failure.message}
        ) from failure
    except Exception as failure:
        raise HTTPException(
            status_code=502,
            detail={"code": "provider_failure", "message": "無法產生報告，請稍後再試。"},
        ) from failure
    return await repository.save_report(conversation_id, position, report)
