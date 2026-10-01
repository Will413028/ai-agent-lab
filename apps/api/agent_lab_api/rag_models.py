from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field

from .contracts import ChatRequest
from .conversation_models import StrictModel

RelationshipStatus = Literal["general", "single", "dating", "married"]


class EmbeddingProfile(StrictModel):
    model: str
    version: str
    dimension: int = Field(ge=1, le=4096)


class Document(StrictModel):
    id: UUID
    name: str
    relationship_status: RelationshipStatus
    digest: str
    embedding_model: str
    embedding_version: str
    embedding_dimension: int
    chunk_version: str
    chunk_count: int
    keywords: list[str]
    created_at: datetime


class Citation(StrictModel):
    chunk_id: UUID
    document_id: UUID
    name: str
    relationship_status: RelationshipStatus
    ordinal: int
    content: str
    score: float


class RetrievalOptions(StrictModel):
    relationship_status: RelationshipStatus | None = None
    top_k: int = Field(default=3, ge=1, le=10)
    threshold: float = Field(default=0.25, ge=0, le=1)


class SearchRequest(RetrievalOptions):
    query: str = Field(min_length=1, max_length=2000)


class RetrievalResult(StrictModel):
    original_question: str
    retrieval_query: str
    options: RetrievalOptions
    profile: EmbeddingProfile
    citations: list[Citation]


class TurnRetrieval(RetrievalResult):
    turn_id: UUID


class RagRequest(ChatRequest, RetrievalOptions):
    pass


class RagModels(StrictModel):
    document: Document
    citation: Citation
    retrieval: RetrievalResult
    turn_retrieval: TurnRetrieval
    request: RagRequest
    search: SearchRequest
