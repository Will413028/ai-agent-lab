from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import Field

from .conversation_models import StrictModel
from .tool_models import ToolCall, ToolResult

RunStatus = Literal["running", "succeeded", "failed", "cancelled", "limit"]


class RunRequest(StrictModel):
    goal: str = Field(min_length=1, max_length=2000)
    max_steps: int = Field(default=6, ge=1, le=12)
    max_calls: int = Field(default=12, ge=1, le=24)


class Usage(StrictModel):
    source: Literal["provider", "unknown", "estimated"] = "unknown"
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)


class Started(StrictModel):
    type: Literal["started"] = "started"
    workspace_id: UUID
    provider: Literal["fake", "cloudflare"]
    tools_mode: Literal["fixture", "live"] = "fixture"
    images_mode: Literal["fixture", "live"] = "fixture"


class RuntimeConfig(StrictModel):
    provider: Literal["fake", "cloudflare"]
    tools_mode: Literal["fixture", "live"]
    images_mode: Literal["fixture", "live"]
    persistence_scope: Literal["disabled", "development", "test"]


class State(StrictModel):
    type: Literal["state"] = "state"
    phase: Literal["thinking", "tool_running"]
    step: int = Field(ge=1, le=12)


class Call(StrictModel):
    type: Literal["tool_call"] = "tool_call"
    call: ToolCall


class Result(StrictModel):
    type: Literal["tool_result"] = "tool_result"
    result: ToolResult


class Final(StrictModel):
    type: Literal["done"] = "done"
    status: Literal["succeeded", "failed", "cancelled", "limit"]
    answer: str = Field(max_length=16000)
    code: str | None = None
    usage: Usage = Field(default_factory=Usage)


class RunEvent(StrictModel):
    version: Literal[1] = 1
    run_id: UUID
    sequence: int = Field(ge=0)
    elapsed_ms: int = Field(default=0, ge=0)
    data: Annotated[Started | State | Call | Result | Final, Field(discriminator="type")]


class Run(StrictModel):
    id: UUID
    conversation_id: UUID
    turn_id: UUID
    workspace_id: UUID
    goal: str
    status: RunStatus
    max_steps: int
    max_calls: int
    answer: str
    error_code: str | None
    created_at: datetime
    finished_at: datetime | None
    events: list[RunEvent] = Field(default_factory=list)


class RunModels(StrictModel):
    request: RunRequest
    run: Run
    event: RunEvent
    config: RuntimeConfig
