from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

Scenario = Literal["normal", "slow", "rate_limit", "quota", "timeout", "dependency_failure"]
ErrorCode = Literal[
    "rate_limited", "quota_exhausted", "provider_timeout", "dependency_failure", "provider_failure"
]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=2000)
    scenario: Scenario = "normal"


class EventBase(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1]
    request_id: UUID
    sequence: int = Field(ge=0)


class DeltaEvent(EventBase):
    type: Literal["delta"]
    text: str = Field(min_length=1)


class DoneEvent(EventBase):
    type: Literal["done"]
    usage: None  # Fake provider has no measured token/Neuron usage.


class ErrorEvent(EventBase):
    type: Literal["error"]
    code: ErrorCode
    message: str
    retryable: bool


ChatEvent = Annotated[DeltaEvent | DoneEvent | ErrorEvent, Field(discriminator="type")]
EVENT_ADAPTER = TypeAdapter(ChatEvent)


def encode_event(event: DeltaEvent | DoneEvent | ErrorEvent) -> str:
    return (
        f"event: {event.type}\n"
        f"id: {event.request_id}:{event.sequence}\n"
        f"data: {event.model_dump_json()}\n\n"
    )
