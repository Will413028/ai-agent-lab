import hashlib
import re
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from .embeddings import Embedder, profile_for, validate_vectors
from .rag_models import Citation, Document, EmbeddingProfile, RelationshipStatus, RetrievalOptions
from .repository import NotFound, Repository

MAX_UPLOAD_BYTES = 512 * 1024
MAX_CHUNKS = 256
CHUNK_SIZE = 600
CHUNK_OVERLAP = 80
CHUNK_VERSION = "paragraph-600-overlap80-v1"
DOCUMENT_COLUMNS = (
    "id,name,relationship_status,digest,embedding_model,embedding_version,"
    "embedding_dimension,chunk_version,chunk_count,keywords,created_at"
)


class KnowledgeConflict(Exception):
    pass


def read_markdown(name: str, content: bytes) -> str:
    if (
        not name
        or len(name) > 160
        or "/" in name
        or "\\" in name
        or not name.lower().endswith(".md")
    ):
        raise ValueError("請匯入檔名長度不超過 160 字的 .md 文件。")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("文件不能超過 512 KiB。")
    try:
        text = content.decode("utf-8-sig").replace("\r\n", "\n").strip()
    except UnicodeDecodeError:
        raise ValueError("文件必須使用 UTF-8 編碼。") from None
    if not text or "\x00" in text:
        raise ValueError("文件內容不能為空或含 NUL。")
    return text


def split_markdown(text: str) -> list[str]:
    chunks: list[str] = []
    pending = ""
    for paragraph in re.split(r"\n\s*\n", text):
        if not paragraph.strip():
            continue
        candidate = (pending + "\n\n" + paragraph).strip()
        if len(candidate) <= CHUNK_SIZE:
            pending = candidate
            continue
        if pending:
            chunks.append(pending)
        pending = paragraph
        while len(pending) > CHUNK_SIZE:
            chunks.append(pending[:CHUNK_SIZE])
            pending = pending[CHUNK_SIZE - CHUNK_OVERLAP :]
    if pending:
        chunks.append(pending)
    if not chunks or len(chunks) > MAX_CHUNKS:
        raise ValueError("文件需要 1–256 個區塊；請拆成較小的文件。")
    return chunks


def keywords(text: str) -> list[str]:
    headings = re.findall(r"(?m)^#{1,6}\s+(.+)$", text)
    terms = headings + re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text)
    return list(dict.fromkeys(term[:60] for term in terms))[:5]


def vector_literal(vector: list[float]) -> str:
    return "[" + ",".join(str(value) for value in vector) + "]"


class KnowledgeStore:
    def __init__(self, repository: Repository):
        self.repository = repository

    async def _profile(self, db, profile: EmbeddingProfile, *, initialize: bool = False):
        cursor = await db.execute("SELECT model,version,dimension FROM agent_lab.embedding_profile")
        row = await cursor.fetchone()
        if row is None:
            if initialize:
                await db.execute(
                    "INSERT INTO agent_lab.embedding_profile (model,version,dimension) "
                    "VALUES (%s,%s,%s)",
                    (profile.model, profile.version, profile.dimension),
                )
            return
        if EmbeddingProfile.model_validate(row) != profile:
            raise KnowledgeConflict("Embedding profile changed; explicitly rebuild the index")

    async def ingest(
        self, name: str, markdown: str, status: RelationshipStatus, embedder: Embedder
    ) -> Document:
        digest = hashlib.sha256(markdown.encode()).hexdigest()
        # Reuse the persisted embedding namespace before spending any provider requests.
        async with self.repository.connection() as db:
            await db.execute("SELECT pg_advisory_xact_lock(hashtext('agent_lab.knowledge'))")
            cursor = await db.execute(
                f"SELECT {DOCUMENT_COLUMNS} FROM agent_lab.documents "
                "WHERE digest=%s AND relationship_status=%s",
                (digest, status),
            )
            existing = await cursor.fetchone()
            if existing is not None:
                document = Document.model_validate(existing)
                if (document.embedding_model, document.embedding_version) != (
                    embedder.model,
                    embedder.version,
                ):
                    raise KnowledgeConflict("Embedding namespace changed; explicitly rebuild")
                return document
        chunks = split_markdown(markdown)
        vectors = validate_vectors(await embedder.embed(chunks), len(chunks))
        profile = profile_for(embedder, vectors)
        async with self.repository.connection() as db:
            await db.execute("SELECT pg_advisory_xact_lock(hashtext('agent_lab.knowledge'))")
            await self._profile(db, profile, initialize=True)
            cursor = await db.execute(
                f"SELECT {DOCUMENT_COLUMNS} FROM agent_lab.documents "
                "WHERE digest=%s AND relationship_status=%s",
                (digest, status),
            )
            existing = await cursor.fetchone()
            if existing:
                return Document.model_validate(existing)
            document_id = uuid4()
            cursor = await db.execute(
                "INSERT INTO agent_lab.documents "
                "(id,name,relationship_status,digest,markdown,embedding_model,embedding_version,"
                "embedding_dimension,chunk_version,chunk_count,keywords) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                f"RETURNING {DOCUMENT_COLUMNS}",
                (
                    document_id,
                    name,
                    status,
                    digest,
                    markdown,
                    profile.model,
                    profile.version,
                    profile.dimension,
                    CHUNK_VERSION,
                    len(chunks),
                    Jsonb(keywords(markdown)),
                ),
            )
            document = Document.model_validate(await cursor.fetchone())
            async with db.cursor() as cursor:
                await cursor.executemany(
                    "INSERT INTO agent_lab.chunks "
                    "(id,document_id,ordinal,content,dimension,embedding) "
                    "VALUES (%s,%s,%s,%s,%s,%s::vector)",
                    [
                        (
                            uuid4(),
                            document_id,
                            index,
                            chunk,
                            profile.dimension,
                            vector_literal(vector),
                        )
                        for index, (chunk, vector) in enumerate(zip(chunks, vectors, strict=True))
                    ],
                )
            return document

    async def list(self) -> list[Document]:
        async with self.repository.connection() as db:
            cursor = await db.execute(
                f"SELECT {DOCUMENT_COLUMNS} FROM agent_lab.documents ORDER BY created_at DESC,id"
            )
            return [Document.model_validate(row) for row in await cursor.fetchall()]

    async def delete(self, document_id: UUID):
        async with self.repository.connection() as db:
            await db.execute("SELECT pg_advisory_xact_lock(hashtext('agent_lab.knowledge'))")
            cursor = await db.execute(
                "DELETE FROM agent_lab.documents WHERE id=%s RETURNING id", (document_id,)
            )
            if await cursor.fetchone() is None:
                raise NotFound
            await db.execute(
                "DELETE FROM agent_lab.embedding_profile "
                "WHERE NOT EXISTS (SELECT 1 FROM agent_lab.documents)"
            )

    async def search(
        self, query: str, options: RetrievalOptions, embedder: Embedder
    ) -> tuple[EmbeddingProfile, list[Citation]]:
        vectors = validate_vectors(await embedder.embed([query]), 1)
        profile = profile_for(embedder, vectors)
        async with self.repository.connection() as db:
            # The lock keeps deletion/reindex/profile reads and vectors in one coherent snapshot.
            await db.execute("SELECT pg_advisory_xact_lock(hashtext('agent_lab.knowledge'))")
            await self._profile(db, profile)
            cursor = await db.execute(
                "SELECT c.id AS chunk_id,c.document_id,d.name,d.relationship_status,"
                "c.ordinal,c.content,1-(c.embedding <=> %s::vector) AS score "
                "FROM agent_lab.chunks c JOIN agent_lab.documents d ON d.id=c.document_id "
                "WHERE (%s::text IS NULL OR d.relationship_status IN ('general',%s)) "
                "AND 1-(c.embedding <=> %s::vector) >= %s "
                "ORDER BY score DESC,c.id LIMIT %s",
                (
                    vector_literal(vectors[0]),
                    options.relationship_status,
                    options.relationship_status,
                    vector_literal(vectors[0]),
                    options.threshold,
                    options.top_k,
                ),
            )
            return profile, [Citation.model_validate(row) for row in await cursor.fetchall()]

    async def reindex(self, embedder: Embedder) -> list[Document]:
        async with self.repository.connection() as db:
            cursor = await db.execute(
                "SELECT id,digest,markdown FROM agent_lab.documents ORDER BY id"
            )
            original = await cursor.fetchall()
        if not original:
            return []
        prepared = []
        profile = None
        for row in original:
            chunks = split_markdown(row["markdown"])
            vectors = validate_vectors(await embedder.embed(chunks), len(chunks))
            current = profile_for(embedder, vectors)
            if profile is not None and current != profile:
                raise KnowledgeConflict("Embedding profile changed during reindex")
            profile = current
            prepared.append((row["id"], chunks, vectors))
        assert profile is not None
        async with self.repository.connection() as db:
            await db.execute("SELECT pg_advisory_xact_lock(hashtext('agent_lab.knowledge'))")
            cursor = await db.execute("SELECT id,digest FROM agent_lab.documents ORDER BY id")
            if await cursor.fetchall() != [
                {"id": r["id"], "digest": r["digest"]} for r in original
            ]:
                raise KnowledgeConflict("Documents changed during reindex; retry explicitly")
            await db.execute("DELETE FROM agent_lab.chunks")
            await db.execute("DELETE FROM agent_lab.embedding_profile")
            await self._profile(db, profile, initialize=True)
            for document_id, chunks, vectors in prepared:
                await db.execute(
                    "UPDATE agent_lab.documents SET embedding_model=%s,embedding_version=%s,"
                    "embedding_dimension=%s,chunk_version=%s,chunk_count=%s WHERE id=%s",
                    (
                        profile.model,
                        profile.version,
                        profile.dimension,
                        CHUNK_VERSION,
                        len(chunks),
                        document_id,
                    ),
                )
                async with db.cursor() as cursor:
                    await cursor.executemany(
                        "INSERT INTO agent_lab.chunks "
                        "(id,document_id,ordinal,content,dimension,embedding) "
                        "VALUES (%s,%s,%s,%s,%s,%s::vector)",
                        [
                            (
                                uuid4(),
                                document_id,
                                i,
                                text,
                                profile.dimension,
                                vector_literal(vector),
                            )
                            for i, (text, vector) in enumerate(zip(chunks, vectors, strict=True))
                        ],
                    )
        return await self.list()
