from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NewConversation(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(default="新的戀愛諮詢", min_length=1, max_length=80)


class Conversation(StrictModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime


class Turn(StrictModel):
    id: UUID
    conversation_id: UUID
    position: int
    question: str
    answer: str
    status: Literal["running", "completed", "failed", "cancelled"]
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None


class ConversationDetail(Conversation):
    turns: list[Turn]


class PromptMessage(StrictModel):
    role: Literal["system", "user", "assistant"]
    content: str


class LoveReport(StrictModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=1, max_length=120)
    suggestions: list[Annotated[str, Field(min_length=1, max_length=1200)]] = Field(
        min_length=1, max_length=5
    )


class SavedReport(StrictModel):
    id: UUID
    conversation_id: UUID
    source_position: int
    content: LoveReport
    created_at: datetime


class ApiModels(StrictModel):
    conversation: Conversation
    detail: ConversationDetail
    report: SavedReport
    new_conversation: NewConversation
