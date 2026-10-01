from typing import Literal

from pydantic import Field

from .conversation_models import StrictModel
from .tool_models import SearchQuery


class ImageResult(StrictModel):
    title: str
    url: str
    source_url: str
    artist: str
    license: str
    license_url: str


class ImageSearchResult(StrictModel):
    provider: str
    images: list[ImageResult] = Field(max_length=5)


class ImageSearchRequest(StrictModel):
    query: SearchQuery


class ImageToolError(StrictModel):
    code: Literal[
        "dependency_failure", "tool_timeout", "network_blocked", "size_limit", "invalid_arguments"
    ]


class ImageModels(StrictModel):
    result: ImageSearchResult
    request: ImageSearchRequest
