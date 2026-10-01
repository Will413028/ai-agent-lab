from typing import Annotated, Any, Literal
from uuid import UUID

from pydantic import Field

from .conversation_models import StrictModel

SearchQuery = Annotated[str, Field(min_length=1, max_length=500)]


class Artifact(StrictModel):
    id: UUID
    workspace_id: UUID
    name: str
    media_type: str
    size: int = Field(ge=0)


class ToolCall(StrictModel):
    id: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1, max_length=80)
    arguments: dict[str, Any]


class ToolResult(StrictModel):
    tool_call_id: str
    name: str
    status: Literal["success", "error"]
    data: dict[str, Any] | None = None
    code: str | None = None
    message: str | None = None


class ToolDefinition(StrictModel):
    name: str
    description: str
    parameters: dict[str, Any]
    side_effect: bool


class ToolRequest(StrictModel):
    workspace_id: UUID
    calls: list[ToolCall] = Field(min_length=1, max_length=8)


class Workspace(StrictModel):
    id: UUID


class ToolModels(StrictModel):
    artifact: Artifact
    call: ToolCall
    result: ToolResult
    definition: ToolDefinition
    request: ToolRequest
    workspace: Workspace
