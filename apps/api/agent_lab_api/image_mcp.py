import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import jsonschema
from mcp import Client, StdioServerParameters
from mcp.shared.exceptions import MCPError
from mcp_types import REQUEST_TIMEOUT
from pydantic import TypeAdapter

from .artifacts import ToolFailure
from .image_models import ImageSearchResult, ImageToolError
from .tool_models import SearchQuery, ToolDefinition


class ImageMCP:
    def __init__(
        self,
        mode: str = "fixture",
        *,
        deadline: float = 30,
        parameters=None,
        call_deadline: float | None = None,
    ):
        self.mode = mode
        self.deadline = deadline
        self.call_deadline = call_deadline or deadline
        self.parameters = parameters or StdioServerParameters(
            command=sys.executable,
            args=["-m", "agent_lab_api.image_mcp_server", "--mode", mode],
            cwd=Path(__file__).resolve().parents[1],
            # No Cloudflare credentials are forwarded to this independent image process.
            env={"PYTHONPATH": str(Path(__file__).resolve().parents[1])},
        )

    @asynccontextmanager
    async def session(self):
        try:
            async with asyncio.timeout(self.deadline):
                # Auto negotiation timed out in this environment. Both eras are supported
                # by SDK 2.2; pin initialize until modern negotiation is revalidated.
                async with Client(
                    self.parameters, mode="legacy", read_timeout_seconds=self.deadline
                ) as client:
                    yield client
        except TimeoutError as failure:
            raise ToolFailure("tool_timeout", "圖片 MCP 呼叫逾時。") from failure
        except ToolFailure:
            raise
        except Exception as failure:

            def typed_error(error):
                if isinstance(error, ToolFailure):
                    return error
                if isinstance(error, TimeoutError) or (
                    isinstance(error, MCPError) and error.code == REQUEST_TIMEOUT
                ):
                    return ToolFailure("tool_timeout", "圖片 MCP 呼叫逾時。")
                if isinstance(error, BaseExceptionGroup):
                    for child in error.exceptions:
                        if found := typed_error(child):
                            return found
                return None

            if known := typed_error(failure):
                raise known from failure
            raise ToolFailure("dependency_failure", "圖片 MCP 服務無法使用。") from failure

    async def discover(self) -> list[ToolDefinition]:
        async with self.session() as client:
            return await self.definitions(client)

    async def definitions(self, client) -> list[ToolDefinition]:
        found = await client.list_tools()
        if found.next_cursor is not None or len(found.tools) != 1:
            raise ToolFailure("dependency_failure", "圖片 MCP 工具清單不符合契約。")
        tool = found.tools[0]
        if tool.name != "searchImages":
            raise ToolFailure("dependency_failure", "圖片 MCP 缺少搜尋工具。")
        jsonschema.Draft202012Validator.check_schema(tool.input_schema)
        properties = tool.input_schema.get("properties", {})
        expected = TypeAdapter(SearchQuery).json_schema()
        actual = properties.get("query", {})
        if any(actual.get(key) != value for key, value in expected.items()) or (
            tool.input_schema.get("required") != ["query"] or set(properties) != {"query"}
        ):
            raise ToolFailure("dependency_failure", "圖片 MCP 參數 schema 不符合契約。")
        return [
            ToolDefinition(
                name=tool.name,
                description=tool.description or "搜尋圖片",
                parameters=tool.input_schema,
                side_effect=False,
            )
        ]

    async def search(self, query: str) -> ImageSearchResult:
        async with self.session() as client:
            definition = (await self.definitions(client))[0]
            try:
                jsonschema.validate({"query": query}, definition.parameters)
            except jsonschema.ValidationError as failure:
                raise ToolFailure("invalid_arguments", "圖片搜尋參數不符合契約。") from failure
            result = await client.call_tool(
                "searchImages", {"query": query}, read_timeout_seconds=self.call_deadline
            )
            if result.is_error:
                # The one fixed local server emits only an allowlisted code envelope.
                # Arbitrary upstream diagnostic text is never forwarded to the UI.
                codes = {
                    "tool_timeout": "圖片搜尋逾時。",
                    "network_blocked": "圖片來源被網路規則阻擋。",
                    "size_limit": "圖片來源回傳超過上限。",
                    "invalid_arguments": "圖片搜尋參數不符合契約。",
                    "dependency_failure": "圖片搜尋來源無法使用。",
                }
                if result.structured_content is not None:
                    error = ImageToolError.model_validate(result.structured_content)
                    raise ToolFailure(error.code, codes[error.code])
                raise ToolFailure("dependency_failure", "圖片搜尋來源無法使用。")
            if result.structured_content is None:
                raise ToolFailure("dependency_failure", "圖片 MCP 回傳格式不正確。")
            return ImageSearchResult.model_validate(result.structured_content)
